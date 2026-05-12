from data_loader.config import get_settings
from data_loader.jobs.poller import run_worker_forever
from data_loader.shared.logging import configure_logging


def run() -> None:
    configure_logging()
    settings = get_settings()
    if settings.ingest_mode == "push":
        from data_loader.http_app import run as run_http

        run_http()
    else:
        run_worker_forever()


if __name__ == "__main__":
    run()
