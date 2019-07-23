# twilio-aws-ivr - A simple Twilio & AWS powered IVR

A basic, but configurable IVR implemented in [Python](https://www.python.org/), deployed with [AWS](https://aws.amazon.com/) & [Chalice](https://github.com/aws/chalice) and telephony via [Twilio](https://www.twilio.com/).

## Prerequisites

* An [Amazon Web Services (AWS)](https://aws.amazon.com/) account
* A [Twilio](https://www.twilio.com/) account
* [Python 3](https://www.python.org/) & [pip3](https://pip.pypa.io/en/stable/) installed locally
* [AWS CLI](https://aws.amazon.com/cli/) installed & configured and a user with administrative permissions
* [direnv](https://direnv.net/) installed & configured _(optional, but recommended)_

## Features

* Highly-available, AWS lambda/API gateway powered IVR
* IVR greeting, main menu and configurable actions
* Redirect, hangup, call forwarding & voicemail actions
* Conditional day/hours checking support

## Setup

Clone the project repository.

In a terminal, go to the project directory and initialise with: `direnv allow`. Once complete you will have a python 3 virtual environment for this project (as long as you are within the project), if you don't want to install `direnv` then you'll need to setup your own virtual env.

Run `./init.sh` to install the relevant python packages and configure some elements of the repository.

Edit/configure the example `config.ini`. Please refer to the configuration section which covers this in detail. The default configuration will not work if deployed.

As part of configuring your IVR, you will almost certainly need to create some recordings. If you don't fancy making your own voice recordings, an easy way to achieve high-quality recordings is by using [AWS's Polly](https://aws.amazon.com/polly/) service.

Upload your mp3s to either [Twilio's Assets](https://www.twilio.com/console/runtime/assets/public) area in the "Runtime" section, or alternatively, somewhere like [AWS S3](https://aws.amazon.com/s3/). You can then reference the URLs to your uploaded recordings in your config file.

When ready deploy your IVR with `chalice deploy` if successful the command will print out an API endpoint.

You can then go back into your `config.ini` and set the `lambda_ping_endpoint` in the `[aws]` section. The value should look something like this: `https://APIGWID.execute-api.AWSREGION.amazonaws.com/api/ping`. The "ping" endpoint is a simple action which will be hit regularly by AWS Cloudwatch events to keep the lambda function active & warm to avoid any initial cold-start delays if someone calls your IVR after a period of inactivity.

Login to Twilio and select the number you want to use with this IVR and in its configuration section ensure the following items are set:

* Accept incoming: "Voice calls"
* Configure with: "Webhooks..."
* A call comes in: "Webhook" and then the API endpoint which should look something like: `https://APIGWID.execute-api.AWSREGION.amazonaws.com/api/ivr`

Hit `Save` to commit these changes.

Now try and ring your Twilio number and test your IVR. If you receive the Twilio voice error message you can check the logs via `chalice logs` and also from with Twilio's admin panel.

## Configuration

The `config.ini` file is broken into different sections, some pre-defined and some user-defined. Each time you update your configuration file you will need to redeploy your IVR.

### [twilio] section

Twilio configuration data.

| Name          | Description              | Mandatory? |
|---------------|--------------------------|------------|
| `account_sid` | Your twilio account SID  | Yes        |
| `auth_token`  | Your twilio auth token   | Yes        |

### [aws] section

AWS & Chalice configuration data.

| Name                             | Description                                     | Mandatory? |
|----------------------------------|-------------------------------------------------|------------|
| `lambda_ping_endpoint`           | The location of your IVR endpoint to hit        | No         |
| `lambda_ping_frequency_minutes`  | How often the lambda should be hit (in minutes) | No<sup>1</sup>         |
| `chalice_debug`                  | Enable/disable chalice debugging                | No         |

### [ivr] section

General configuration options for your IVR.

| Name       | Description                                                                               | Mandatory? |
|------------|-------------------------------------------------------------------------------------------|------------|
| `timezone` | The [name of your timezone](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) (e.g., `Europe/London`) | Yes        |

### [ivr\_welcome] section

Configuration options for the initial call-answering welcome message.

| Name                     | Description                                                   | Mandatory?     |
|--------------------------|---------------------------------------------------------------|----------------|
| `play_sample`            | The URL of the recording to play on answering                 | No             |
| `hours`                  | The name of hours section to check                            | No             |
| `hours_action_on_closed` | The name of the action to execute if out of the defined hours | No<sup>2</sup> |

### [ivr\_menu] section

| Name                           | Description                                                   | Mandatory?     |
|--------------------------------|---------------------------------------------------------------|----------------|
| `play_sample`                  | The URL of the recording to play on answering                 | No             |
| `pause`                        | The amount of time to pause in seconds before looping         | No             |
| `no_input_sample`              | The sample to play if no menu option has been selected        | No             |
| `no_input_max_loops`           | The maximum times to loop the menu on no input                | No             |
| `no_input_action_on_max_loops` | The action to execute when max loops has been achieved        | No             |
| `hours`                        | The name of hours section to check                            | No             |
| `hours_action_on_closed`       | The name of the action to execute if out of the defined hours | No<sup>2</sup> |

### [ivr\_menu\_option\_*] sections

| Name                     | Description                                                   | Mandatory?     |
|--------------------------|---------------------------------------------------------------|----------------|
| `action`                 | The action to execute for the selected menu option            | Yes            |
| `play_sample`            | The URL of the recording to play on answering                 | No             |
| `hours`                  | The name of hours section to check                            | No             |
| `hours_action_on_closed` | The name of the action to execute if out of the defined hours | No<sup>2</sup> |

### [action\_*] sections

Actions are what direct and handle the selected main menu options. There are currently 4 different type of actions you can define. You can define as many actions as are necessary.

#### "forward" action

This action allows you to forward to a phone number which takes the call. You also have some options to redirect the action to another action if the phone number you're forwarding to is busy or doesn't answer etc.

| Name                     | Description                                                     | Mandatory?     |
|--------------------------|-----------------------------------------------------------------|----------------|
| `type`                   | Set to `forward`                                                | Yes            |
| `play_sample`            | The URL of the recording to play on answering                   | No             |
| `phone_number`           | The phone number to forward the call to                         | Yes            |
| `action_on_busy`         | The action to redirect to if the `phone_number` is busy         | Yes            |
| `action_on_no_answer`    | The action to redirect to if the `phone_number` does not answer | Yes            |
| `action_on_failed`       | The action to redirect to if the `phone_number` fails           | Yes            |
| `action_on_canceled`     | The action to redirect to if the `phone_number` cancels         | Yes            |
| `hours`                  | The name of hours section to check                              | No             |
| `hours_action_on_closed` | The name of the action to execute if out of the defined hours   | No<sup>2</sup> |


#### "hangup" action

This action simply hangs up the phone and can optionally play a sample before doing so.

| Name                     | Description                                                   | Mandatory?     |
|--------------------------|---------------------------------------------------------------|----------------|
| `type`                   | Set to `hangup`                                               | Yes            |
| `play_sample`            | The URL of the recording to play on answering                 | No             |
| `hours`                  | The name of hours section to check                            | No             |
| `hours_action_on_closed` | The name of the action to execute if out of the defined hours | No<sup>2</sup> |

#### "redirect" action

This action directs to another action, useful for pointing the user back to the menu for unused menu options and also conditional processing based on "hours" (see below)

| Name                     | Description                                                   | Mandatory?     |
|--------------------------|---------------------------------------------------------------|----------------|
| `type`                   | Set to `redirect`                                             | Yes            |
| `play_sample`            | The URL of the recording to play on answering                 | No             |
| `path`                   | The API path to redirect to                                   | Yes            |
| `hours`                  | The name of hours section to check                            | No             |
| `hours_action_on_closed` | The name of the action to execute if out of the defined hours | No<sup>2</sup> |

#### "voicemail" action

This action takes a voicemail message and sends the user an SMS link to listen to the message.

| Name                       | Description                                                   | Mandatory?     |
|----------------------------|---------------------------------------------------------------|----------------|
| `type`                     | Set to `voicemail`                                            | Yes            |
| `play_sample`              | The URL of the recording to play on answering                 | Yes            |
| `hangup_sample`            | The sample to play just before hanging up the call            | Yes            |
| `voicemail_alert_sms_from` | The twilio number to send the SMS from                        | Yes            |
| `voicemail_alert_sms_to`   | The mobile number to send the SMS to                          | Yes            |
| `voicemail_timeout`        | The number of seconds to wait until it stops recording        | Yes            |
| `voicemail_max_length`     | The maximum length allowed in seconds for a single voicemail  | Yes            |
| `hours`                    | The name of hours section to check                            | No             |
| `hours_action_on_closed`   | The name of the action to execute if out of the defined hours | No<sup>2</sup> |

### [hours\_*] sections

Hours allow you to conditionally

**Note**: that for any section which supports the "hours" option, it will process this before any other options. For example if you are "out of hours" and have a `play_sample` defined, it will not play this recording but will instead execute the `hours_action_on_closed` definition first instead.

| Name                       | Description              | Mandatory?      |
|----------------------------|--------------------------|-----------------|
| `mon`                      | Time range for Monday    | Yes<sup>3</sup> |
| `tue`                      | Time range for Tuesday   | Yes<sup>3</sup> |
| `wed`                      | Time range for Wednesday | Yes<sup>3</sup> |
| `thu`                      | Time range for Thursday  | Yes<sup>3</sup> |
| `fri`                      | Time range for Friday    | Yes<sup>3</sup> |
| `sat`                      | Time range for Saturday  | Yes<sup>3</sup> |
| `sun`                      | Time range for Sunday    | Yes<sup>3</sup> |

## To be implemented

* Unit tests :)
* Better hours support (e.g., shorthand for all day, multiple range support for a single day)

---

## Footnotes

<sup>1</sup> Required if `lambda_ping_endpoint` is defined.

<sup>2</sup> Required if `hours` is defined.

<sup>3</sup> Required but can be left blank meaning (closed all day)
