import os
import re
import datetime
import configparser
from abc import ABC, abstractmethod

import pytz
from chalice import Chalice
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

from chalicelib.ext import url_of


class IvrError(Exception):
    pass


class IvrSectionError(IvrError):
    pass


class IvrSectionNotFoundError(IvrError):
    pass


class IvrSectionFieldError(IvrSectionError):
    pass


class IvrSectionInvalidFieldError(IvrSectionFieldError):
    pass


class IvrSectionMissingMandatoryFieldError(IvrSectionFieldError):
    pass


class Ivr:
    """
    The main controlling class for the IVR script
    """

    def __init__(self, config_path: str, app: Chalice):
        """
        Object initialisation
        """

        self.config = self._parse_config(config_path)
        self.app = app

        # Turn on chalice debugging if it's enable in config
        self.app.debug = self.config.getboolean(
                        'aws',
                        'chalice_debug',
                        fallback=False
                    )

        # Set timezone so any hours checks are accurate
        if not self.config.get('ivr', 'timezone'):
            raise IvrError('IVR timezone not set in config')

        self.timezone = pytz.timezone(self.config.get('ivr', 'timezone'))

        twilio_account_sid = self.config.get('twilio', 'account_sid')
        twilio_auth_token = self.config.get('twilio', 'auth_token')

        if not twilio_account_sid:
            raise IvrSectionError(
                'No twilio account_sid defined in config file'
            )

        if not twilio_auth_token:
            raise IvrSectionError(
                'No twilio auth_token defined in config file'
            )

        self.twilio_client = Client(twilio_account_sid, twilio_auth_token)

    def _parse_config(self, config_path: str):
        """
        Parse provided config
        """

        if not os.path.exists(config_path):
            raise IvrError(f'Invalid configuration path: {config_path}')

        config = configparser.ConfigParser()

        if not len(config.read(config_path)):
            raise IvrError('Failed parsing config')

        return config

    def get_config_section(self, section_name: str):
        try:
            return dict(self.config[section_name])
        except KeyError:
            raise IvrSectionNotFoundError(section_name)

    def get_welcome_section(self):
        return IvrWelcomeSection(self, self.get_config_section('ivr_welcome'))

    def get_menu_section(self):
        return IvrMenuSection(self, self.get_config_section('ivr_menu'))

    def get_menu_option_section(self, option: int):
        assert 0 <= option <= 9, f'Invalid menu option value: {option}'

        return IvrMenuOptionSection(
            self,
            option,
            self.get_config_section(f'ivr_menu_option_{option}')
        )

    def get_action_section(self, name: str):
        try:
            config_section = self.get_config_section(f'action_{name}')
        except IvrSectionNotFoundError:
            raise IvrError(f'Invalid action: {name}')

        action_types = {
            'redirect': IvrActionRedirect,
            'forward': IvrActionForward,
            'voicemail': IvrActionVoicemail,
            'hangup': IvrActionHangup,
        }

        if 'type' not in config_section:
            raise IvrSectionMissingMandatoryFieldError('type')
        elif config_section['type'] not in action_types:
            raise IvrError(
                f"Invalid action type specified: {config_section['type']}"
            )

        return action_types[config_section['type']](self, name, config_section)

    def get_hours_section(self, name: str):
        return IvrHoursSection(
            self,
            name,
            self.get_config_section(f'hours_{name}')
        )

    def get_now(self):
        """
        Returns a timezone correct current date/time object
        """

        return datetime.datetime.now(tz=self.timezone)

    def test(self, verbose=True):
        """
        Get each section of the config file
        (and in doing so perform a basic mandatory field test on it)
        """

        if verbose:
            print('Testing [ivr_welcome] section')
        self.get_welcome_section()

        if verbose:
            print('Testing [ivr_menu] section')
        self.get_menu_section()

        for section_name in range(9):
            if verbose:
                print(f'Testing [ivr_menu_option_{section_name}] section')
            self.get_menu_option_section(section_name)

        for section_name in self.config.keys():
            if section_name.startswith('action_'):
                if verbose:
                    print(f'Testing [{section_name}] section')
                self.get_action_section(section_name[7:])

        for section_name in self.config.keys():
            if section_name.startswith('hours_'):
                if verbose:
                    print(f'Testing [{section_name}] section')
                self.get_hours_section(section_name[6:])

        if verbose:
            print('Configuration looks correct.')


class IvrSection(ABC):
    """
    Abstract base for all IVR script related sections represented in the config
    """

    def __init__(self, ivr: Ivr, name: str, section_data: dict,
                 valid_fields: set = set(), mandatory_fields: set = set()):
        self.ivr = ivr
        self.name = name
        self.section_data = section_data

        if valid_fields:
            self._check_valid_fields(valid_fields)

        if mandatory_fields:
            self._check_mandatory_fields(mandatory_fields)

        self.has_hours = 'hours' in self.section_data.keys()

    def _check_mandatory_fields(self, mandatory_fields: set):
        """
        Confirms mandatory fields are defined in a config section
        """

        section_data_keys = self.section_data.keys()

        for field in mandatory_fields:
            if field not in section_data_keys:
                raise IvrSectionMissingMandatoryFieldError(field)

    def _check_valid_fields(self, valid_fields: set):
        """
        Defines all mandatory & optional sections fields
        """

        for field in self.section_data.keys():
            if field not in valid_fields:
                raise IvrSectionInvalidFieldError(field)

    def handle_hours(self):
        """
        Processes any hours definitions in a given section
        """

        resp = None

        if not self.has_hours:
            return resp

        hours_section = self.ivr.get_hours_section(self.section_data['hours'])

        if not hours_section.is_within_hours():
            if 'hours_action_on_closed' not in self.section_data:
                raise IvrSectionFieldError(
                    (f'Required field \'hours_action_on_closed\' ',
                        'not defined in: {self.name}')
                )

            resp = VoiceResponse()
            resp.redirect(
                self.url_of(
                    '/ivr/action/'+self.section_data['hours_action_on_closed']
                )
            )

        return resp

    def url_of(self, path: str):
        return url_of(self.ivr.app, path)

    @abstractmethod
    def execute(self):
        pass


class IvrWelcomeSection(IvrSection):
    """
    The root welcome section of the IVR script
    """

    def __init__(self, ivr: Ivr, section_data: dict):
        super().__init__(
            ivr,
            'welcome',
            section_data,
            {
                'hours',
                'hours_action_on_closed',
                'play_sample',
            }
        )

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        if 'play_sample' in self.section_data.keys():
            resp.play(self.section_data['play_sample'])

        resp.redirect(self.url_of('/ivr/menu'))

        return str(resp)


class IvrMenuSection(IvrSection):
    """
    The main menu section of the IVR script
    """

    def __init__(self, ivr: Ivr, section_data: dict):
        super().__init__(
            ivr,
            'menu',
            section_data,
            {
                'hours',
                'hours_action_on_closed',
                'play_sample',
                'no_input_sample',
                'no_input_max_loops',
                'no_input_action_on_max_loops',
                'pause'
            },
            {
                'play_sample',
            }
        )

        self.loop_count = 1

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        gather = Gather()
        gather.play(self.section_data['play_sample'], digits=1)

        pause = 2
        if 'pause' in self.section_data.keys():
            pause = int(self.section_data['pause'])

        gather.pause(length=pause)

        resp.append(gather)

        if ('no_input_max_loops' in self.section_data.keys()
                and self.loop_count
                >= int(self.section_data['no_input_max_loops'])):
            if 'no_input_action_on_max_loops' in self.section_data.keys():
                resp.redirect(
                    self.url_of(
                        '/ivr/action/'+self.section_data['no_input_action_on_max_loops']
                    )
                )
            else:
                resp.hangup()

        if 'no_input_sample' in self.section_data.keys():
            resp.play(self.section_data['no_input_sample'])

        resp.redirect(self.url_of(f'/ivr/menu?loop_count={self.loop_count}'))

        return str(resp)


class IvrMenuOptionSection(IvrSection):
    """
    A menu option of the IVR script
    """

    def __init__(self, ivr: Ivr, option: int, section_data: dict):
        super().__init__(
            ivr,
            str(option),
            section_data,
            {
                'hours',
                'hours_action_on_closed',
                'play_sample',
                'action',
            },
            {
                'action',
            }
        )

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        if 'play_sample' in self.section_data.keys():
            resp.play(self.section_data['play_sample'])

        resp.redirect(
            self.url_of('/ivr/action/'+self.section_data['action'])
        )

        return str(resp)


class IvrActionSection(IvrSection):
    """
    An IVR script action
    """

    pass


class IvrActionRedirect(IvrActionSection):
    """
    Redirect to another endpoint
    """

    def __init__(self, ivr: Ivr, name: str, section_data: dict):
        super().__init__(
            ivr,
            name,
            section_data,
            {
                'type',
                'hours',
                'hours_action_on_closed',
                'play_sample',
                'path',
            },
            {
                'path',
            }
        )

        if not self.section_data['path']:
            raise IvrSectionError('No path defined')

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        try:
            if self.section_data['play_sample']:
                resp.play(self.section_data['play_sample'])
        except KeyError:
            pass

        resp.redirect(self.url_of(self.section_data['path']))

        return str(resp)


class IvrActionHangup(IvrActionSection):
    """
    Hangup after it has been played
    """

    def __init__(self, ivr: Ivr, name: str, section_data: dict):
        super().__init__(
            ivr,
            name,
            section_data,
            {
                'type',
                'hours',
                'hours_action_on_closed',
                'play_sample',
            }
        )

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        if 'play_sample' in self.section_data.keys():
            resp.play(self.section_data['play_sample'])

        resp.hangup()

        return str(resp)


class IvrActionForward(IvrActionSection):
    """
    Forward the call to a number
    """

    def __init__(self, ivr: Ivr, name: str, section_data: dict):
        super().__init__(
            ivr,
            name,
            section_data,
            {
                'type',
                'hours',
                'hours_action_on_closed',
                'play_sample',
                'phone_number',
                'action_on_busy',
                'action_on_no_answer',
                'action_on_failed',
                'action_on_canceled',
            },
            {
                'phone_number',
                'action_on_busy',
                'action_on_no_answer',
                'action_on_failed',
                'action_on_canceled',
            }
        )

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        if self.section_data['play_sample']:
            resp.play(self.section_data['play_sample'])

        resp.dial(
            self.section_data['phone_number'],
            action=self.url_of(f'/ivr/callback/forward/call_status?initiated_by_section={self.name}'),
            method='POST'
        )

        return str(resp)


class IvrActionVoicemail(IvrActionSection):
    """
    Play a message and then allow callers to leave a voicemail
    """

    def __init__(self, ivr: Ivr, name: str, section_data: dict):
        super().__init__(
            ivr,
            name,
            section_data,
            {
                'type',
                'hours',
                'hours_action_on_closed',
                'play_sample',
                'hangup_sample',
                'voicemail_alert_sms_from',
                'voicemail_alert_sms_to',
                'voicemail_timeout',
                'voicemail_max_length',
            },
            {
                'play_sample',
                'hangup_sample',
                'voicemail_alert_sms_from',
                'voicemail_alert_sms_to',
                'voicemail_timeout',
                'voicemail_max_length',
            }
        )

    def execute(self):
        resp = self.handle_hours()
        if resp is not None:
            return str(resp)

        resp = VoiceResponse()

        if self.section_data['play_sample']:
            resp.play(self.section_data['play_sample'])
            resp.pause(1)

        voicemail_timeout = int(self.section_data['voicemail_timeout'])
        voicemail_max_length = int(self.section_data['voicemail_max_length'])

        resp.record(
            action=self.url_of(f'/ivr/callback/voicemail/hangup?initiated_by_section={self.name}'),
            timeout=voicemail_timeout,
            max_length=voicemail_max_length,
            recording_status_callback=self.url_of(f'/ivr/callback/voicemail/alert_sms?initiated_by_section={self.name}'),
            recording_status_callback_method='POST'
        )

        return str(resp)


class IvrHoursSection(IvrSection):
    """
    An hours section from the IVR config
    """

    weekdays = [
        'mon',
        'tue',
        'wed',
        'thu',
        'fri',
        'sat',
        'sun',
    ]

    def __init__(self, ivr: Ivr, name: str, section_data: dict):
        super().__init__(
            ivr,
            name,
            section_data,
            IvrHoursSection.weekdays,
            IvrHoursSection.weekdays,
        )

        self.data = self._parse_section_data(section_data)

    def _parse_section_data(self, section_data: dict):
        """
        Returns a useful data structure from the config dict
        """

        # Parse the config data into something we can use

        # Initialise data structure to default to closed all day
        data = {
            day: {'from': None, 'to': None} for day in IvrHoursSection.weekdays
        }

        for day in IvrHoursSection.weekdays:
            # Clean up value
            try:
                hours_str = section_data[day].replace(' ', '')
            except KeyError:
                # Doesn't matter if it's not defined when we're iterating
                pass

            # Parse the from/to times
            if hours_str:
                time_regex = r'([01]\d|2[0-3])([0-5]\d)'
                timeframe_regex = f'^{time_regex}-{time_regex}$'

                timeframe_matches = re.match(timeframe_regex, hours_str)

                if timeframe_matches is None:
                    raise IvrError(
                        (f'Invalid timeframe format specified for {day}, ',
                            'it must be in the format HHMM-HHMM')
                    )

                data[day]['from'] = datetime.time(
                    hour=int(timeframe_matches[1]),
                    minute=int(timeframe_matches[2])
                )

                data[day]['to'] = datetime.time(
                    hour=int(timeframe_matches[3]),
                    minute=int(timeframe_matches[4])
                )

        return data

    def is_within_hours(self):
        """
        Check whether the current day/time is within the defined hours
        """

        now = self.ivr.get_now()
        time_now = now.time()
        day_hours = self.data[IvrHoursSection.weekdays[now.weekday()]]

        # Closed all day
        if not day_hours['from'] or not day_hours['to']:
            return False

        return (time_now >= day_hours['from'] and time_now <= day_hours['to'])

    def execute(self):
        return self.is_within_hours()
