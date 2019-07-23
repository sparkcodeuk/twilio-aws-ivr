import sys
import argparse
import configparser

from chalice import Chalice

from chalicelib.ivr import Ivr, IvrError


def cli_main(
    app_name: str,
    version: str,
    default_config_path: str,
    app: Chalice
):
    """
    Command line IVR testing/debugging
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config', '-c',
        type=str,
        help=''.join((
            'Path of the configuration file, ',
            f'(default path: {default_config_path})'
        )),
        default=default_config_path
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Quiet (no output)'
    )
    parser.add_argument(
        '--version', '-v',
        action='store_true',
        help='Print version and exit'
    )

    args = parser.parse_args()

    if args.version:
        print(f'{app_name} v{version}')
        return

    # Instantiating Ivr class tests/parses the config
    if args.quiet:
        try:
            ivr = Ivr(args.config, app)
            ivr.test(verbose=not args.quiet)
        except (configparser.Error, IvrError):
            sys.exit(1)
    else:
        ivr = Ivr(args.config, app)
        ivr.test()
