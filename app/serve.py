"""Run the direct HTTP(S) listener: python -m app.serve."""
import argparse
from contextlib import ExitStack, closing, redirect_stderr, redirect_stdout
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

import uvicorn

from app.config import ROOT_DIR


class TaskLog(RotatingFileHandler):
    """One rotating UTF-8 stream for both outputs of a Windows startup task."""
    terminator = ''

    def write(self, text):
        if text:
            self.handle(logging.LogRecord('serve', logging.INFO, '', 0, text, (), None))
        return len(text)

    def isatty(self):
        return False

    def handleError(self, record):
        # Logging its own disk error to redirected stderr would recurse.
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='HTTPS-сервер Project 2')
    parser.add_argument('--env-file', type=Path, help='Файл конфігурації завдання Windows')
    parser.add_argument('--log-file', type=Path, help='Журнал stdout/stderr поза репозиторієм')
    args = parser.parse_args(argv)
    with ExitStack() as stack:
        if args.log_file:
            path = args.log_file.resolve()
            if path.is_relative_to(ROOT_DIR):
                parser.error('Журнал сервера має бути поза репозиторієм.')
            log = stack.enter_context(closing(TaskLog(path, maxBytes=5 * 1024 * 1024,
                                                      backupCount=3, encoding='utf-8')))
            stack.enter_context(redirect_stdout(log))
            stack.enter_context(redirect_stderr(log))
        if args.env_file:
            if not args.env_file.is_file():
                parser.error('Файл конфігурації не знайдено.')
            os.environ['PROJECT2_ENV_FILE'] = str(args.env_file.resolve())
        try:
            # Loading Settings reads the selected dotenv before validating the listener.
            from app.main import app, network_policy
            config = network_policy.settings
            mode = 'auto' if config.networks is None else 'CIDR'
            networks = ['loopback']
            if not config.loopback_only:
                networks.extend(map(str, network_policy.allowed_networks()))
            scheme = 'https' if config.cert else 'http'
            trust = config.device_trust
            print(f'Project 2 · {scheme}://{config.server_name}:{config.port} · {mode} · '
                  f'дозволено {", ".join(networks)}' + (f' · {trust.summary()}' if trust else ''), flush=True)
            uvicorn.run(trust.application(app) if trust else app, host=config.bind_host, port=config.port,
                        ssl_certfile=str(config.cert) if config.cert else None,
                        ssl_keyfile=str(config.key) if config.key else None,
                        ssl_context_factory=trust.ssl_context if trust else None,
                        proxy_headers=False, forwarded_allow_ips='', server_header=False,
                        reload=False, workers=1, access_log=False)
        except (ValueError, OSError) as error:
            print(f'Помилка запуску Project 2: {error}', file=sys.stderr)
            raise SystemExit(1) from None


if __name__ == '__main__':
    main()
