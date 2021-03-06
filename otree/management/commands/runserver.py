from channels.management.commands import runserver
from channels.management.commands.runserver import WorkerThread, Server
import otree.bots.browser
from django.conf import settings
import otree.common_internal
from channels import channel_layers
import logging
from otree import common_internal
import random
import os

class Command(runserver.Command):

    def handle(self, *args, **options):

        # seems it would be simpler if i just set
        # self.channel_layer = channel_layers['inmemory']
        # in inner_run below, but when I do that, messages don't get sent
        settings.CHANNEL_LAYERS['default'] = settings.CHANNEL_LAYERS['inmemory']

        from otree.common_internal import release_any_stale_locks
        release_any_stale_locks()

        # don't use cached template loader, so that users can refresh files
        # and see the update.
        # kind of a hack to patch it here and to refer it as [0],
        # but can't think of a better way.
        settings.TEMPLATES[0]['OPTIONS']['loaders'] = [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ]

        # so we know not to use Huey
        otree.common_internal.USE_REDIS = False

        # for performance,
        # only run checks when the server starts, not when it reloads
        # (RUN_MAIN is set by Django autoreloader).
        if not os.environ.get('RUN_MAIN'):
            try:
                self.check(display_num_errors=True)
            except Exception as exc:
                common_internal.print_colored_traceback_and_exit(exc)

        super().handle(*args, **options)

    def inner_run(self, *args, **options):
        '''
        Adapted from channels 0.17.3.
        When we upgrade channels, we need to modify this somewhat.

        inner_run does not get run twice with runserver, unlike .handle()
        '''

        # initialize browser bot worker in process memory
        otree.bots.browser.browser_bot_worker = otree.bots.browser.Worker()

        # oTree use in-memory.
        # this is the simplest way to patch tests to use in-memory,
        # while still using Redis in production
        self.channel_layer = channel_layers['default']
        self.channel_layer.router.check_default(
            http_consumer=self.get_consumer(*args, **options),
        )

        addr = '[%s]' % self.addr if self._raw_ipv6 else self.addr
        if addr == '127.0.0.1':
            addr = 'localhost'
        self.stdout.write((
            "Starting server at http://%(addr)s:%(port)s/\n"
            "To quit the server, press Control+C.\n"
        ) % {
            "addr": addr,
            "port": self.port,
        })

        # silence the lines like:
        # 2018-01-10 18:51:18,092 - INFO - worker - Listening on channels
        # http.request, otree.create_session, websocket.connect,
        # websocket.disconnect, websocket.receive
        channels_logger = logging.getLogger('django.channels')
        log_level = channels_logger.level
        channels_logger.level = logging.WARNING
        try:
            for _ in range(4):
                worker = WorkerThread(self.channel_layer, self.logger)
                worker.daemon = True
                worker.start()
        finally:
            channels_logger.setLevel(log_level)

        # Launch server in 'main' thread. Signals are disabled as it's still
        # actually a subthread under the autoreloader.
        try:
            Server(
                channel_layer=self.channel_layer,
                host=self.addr,
                port=int(self.port),
                signal_handlers=not options['use_reloader'],
                action_logger=self.log_action,
                http_timeout=60,  # Shorter timeout than normal as it's dev
                ws_protocols=getattr(settings, 'CHANNELS_WS_PROTOCOLS', None),
            ).run()
        except KeyboardInterrupt:
            shutdown_message = options.get('shutdown_message', '')
            if shutdown_message:
                self.stdout.write(shutdown_message)
            return
