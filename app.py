#!/usr/bin/env python3
# A simple Twilio & AWS powered IVR

import os
import sys

from urllib.parse import parse_qs
from urllib.request import urlopen

from chalice import Chalice, Rate, Response
from twilio.twiml.voice_response import VoiceResponse

from chalicelib.ext import url_of
from chalicelib.cli import cli_main
from chalicelib.ivr import Ivr


# App details & config
__app_name__ = 'twilio-aws-ivr'
__version__ = '1.0.0'
default_config_path = os.path.join('chalicelib', 'config.ini')

app = Chalice(app_name=__app_name__)

# CLI execution
if __name__ == '__main__':
    cli_main(
        app_name=__app_name__,
        version=__version__,
        default_config_path=default_config_path,
        app=app
    )

    sys.exit()


# Lambda execution
ivr = Ivr(default_config_path, app)

lambda_ping_frequency_minutes = ivr.config.getint(
                                    'aws',
                                    'lambda_ping_frequency_minutes',
                                    fallback=0
                                )

if lambda_ping_frequency_minutes != 0:
    assert 1 <= lambda_ping_frequency_minutes <= 60, \
        ('config value: aws.lambda_ping_frequency_minutes '
            'must be between 1 - 60 minutes')


def create_response(response_body: str = ''):
    """
    Create a valid TwiML response payload for API entrypoints
    """

    return Response(
        body=response_body,
        status_code=200,
        headers={'Content-Type': 'text/xml'}
    )


def create_redirect(path: str, say_text: str = None):
    """
    Create an adhoc TwiML redirect
    (useful in case of script errors) with an optional spoken message
    """

    resp = VoiceResponse()

    # Provide some feedback before the redirect
    if say_text is not None:
        resp.say(say_text)

    resp.redirect(url_of(app, path))

    return create_response(str(resp))


def create_hangup(say_text: str = None):
    """
    Create a simple hangup (with an optional spoken message)
    """

    resp = VoiceResponse()

    # Provide some feedback before the redirect
    if say_text is not None:
        resp.say(say_text)

    resp.hangup()

    return create_response(str(resp))


if lambda_ping_frequency_minutes:
    @app.schedule(Rate(lambda_ping_frequency_minutes, unit=Rate.MINUTES))
    def keep_lambda_warm(event_data):
        """
        Responsible for ensuring the lambda function remains warm
        to avoid cold-start delays
        """

        config = ivr.get_config_section('aws')

        ping_endpoint_data = None
        if 'lambda_ping_endpoint' in config:
            ping_endpoint_data = urlopen(config['lambda_ping_endpoint']).read()
            print(f'IVR invoked result: {ping_endpoint_data}')
        else:
            print(
                ('No \'lambda_ping_endpoint\' defined, ',
                    'unable to keep IVR warm')
            )

        return {
            'name': 'keepLambdaWarm',
            'invokedAt': str(ivr.get_now()),
        }


@app.route(
    '/ping',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ping():
    """
    Useful for testing that your IVR lambda is operational
    """

    return {
        'name': 'ping',
        'invokedAt': str(ivr.get_now()),
    }


@app.route(
    '/ivr',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_welcome():
    """
    Main IVR entrypoint
    """

    return create_response(
        ivr.get_welcome_section().execute()
    )


@app.route(
    '/ivr/hangup',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_hangup():
    """
    Hangup the call
    """

    return create_hangup()


@app.route(
    '/ivr/menu',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_menu():
    """
    IVR main menu
    """

    menu_section = ivr.get_menu_section()

    if app.current_request.method == 'POST':
        # Parse form_data to get selected menu option
        form_data = parse_qs(app.current_request.raw_body.decode())

        if 'Digits' in form_data and form_data['Digits']:
            return create_redirect(f"/ivr/menu/{form_data['Digits'][0]}")

        if app.current_request.query_params \
                and 'loop_count' in app.current_request.query_params.keys():
            menu_section.loop_count = \
                int(app.current_request.query_params['loop_count'])+1

    return create_response(
        menu_section.execute()
    )


@app.route(
    '/ivr/menu/{option}',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_menu_option(option=None):
    """
    IVR menu option processing
    """

    try:
        option = int(option)
    except ValueError:
        return create_redirect('/ivr/menu', 'Invalid menu option selected')

    # Main menu + single digit menu bounds checking
    if option is None or not 0 <= option <= 9:
        return create_redirect('/ivr/menu', 'Invalid menu option selected')

    # Process selected menu option
    return create_response(
        ivr.get_menu_option_section(option).execute()
    )


@app.route(
    '/ivr/action/{action}',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_action(action=None):
    """
    IVR action processing
    """

    return create_response(
        ivr.get_action_section(action).execute()
    )


@app.route(
    '/ivr/callback/forward/call_status',
    methods=['POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_callback_forward_call_status(action=None):
    """
    IVR forward action callback
    Check whether the call was successfully forwarded or not
    (if busy provide the option to leave a message)
    """

    # Twilio status to internal status names
    call_status_map = {
        'busy': 'busy',
        'no-answer': 'no_answer',
        'failed': 'failed',
        'canceled': 'canceled',
    }

    # Parse form_data
    form_data = parse_qs(app.current_request.raw_body.decode())

    if 'DialCallStatus' in form_data and form_data['DialCallStatus']:
        twilio_call_status = form_data['DialCallStatus'][0]

        if twilio_call_status in call_status_map:
            # Determine which section initiated this callback
            if 'initiated_by_section' in app.current_request.query_params:
                initiated_by_section = \
                    app.current_request.query_params['initiated_by_section']

                forwarding_action = \
                    ivr.config.get(
                        f'action_{initiated_by_section}',
                        f'action_on_{call_status_map[twilio_call_status]}'
                    )

            return create_redirect(f"/ivr/action/{forwarding_action}")

    return create_hangup()


@app.route(
    '/ivr/callback/voicemail/alert_sms',
    methods=['POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_callback_voicemail_alert_sms():
    """
    Send an SMS alert if a voicemail has been left
    """

    # Parse form_data
    form_data = parse_qs(app.current_request.raw_body.decode())

    if 'RecordingUrl' in form_data \
            and 'RecordingStatus' in form_data \
            and form_data['RecordingStatus'][0] == 'completed':

        if 'initiated_by_section' in app.current_request.query_params:
            initiated_by_section = \
                app.current_request.query_params['initiated_by_section']

            section_data = ivr.config[f'action_{initiated_by_section}']

            ivr.twilio_client.messages.create(
                body='New voicemail: '+str(form_data['RecordingUrl'][0]),
                from_=section_data['voicemail_alert_sms_from'],
                to=section_data['voicemail_alert_sms_to']
            )

    return create_response()


@app.route(
    '/ivr/callback/voicemail/hangup',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def ivr_callback_voicemail_hangup():
    """
    Hangup action after the voicemail has finished
    """

    resp = VoiceResponse()

    # Determine which section initiated this callback
    if 'initiated_by_section' in app.current_request.query_params:
        initiated_by_section = \
            app.current_request.query_params['initiated_by_section']

        hangup_sample = \
            ivr.config.get(f'action_{initiated_by_section}', 'hangup_sample')

        resp.play(hangup_sample)
        resp.hangup()

    return create_response(str(resp))
