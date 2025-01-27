# stdlib
from typing import Any

# third party
from raven import Client

# syft absolute
from syft.core.common.message import SignedImmediateSyftMessageWithoutReply
from syft.core.node.common.action.exceptions import RetriableError
from syft.core.node.common.action.unfinished_task import register_unfinished_task

# grid absolute
from grid.core.celery_app import celery_app
from grid.core.config import settings
from grid.core.node import node

client_sentry = Client(settings.SENTRY_DSN)


# TODO : Should be modified to use exponential backoff (for efficiency)
# Initially we have set 0.1 as the retry time.
# We have set max retries =(1200) 120 seconds


@celery_app.task(bind=True, acks_late=True)
def msg_without_reply(self, obj_msg: Any) -> None:  # type: ignore
    if isinstance(obj_msg, SignedImmediateSyftMessageWithoutReply):
        try:
            node.recv_immediate_msg_without_reply(msg=obj_msg)
        except Exception as e:
            if isinstance(e, RetriableError):
                register_unfinished_task(obj_msg, node)
            else:
                raise e
    else:
        raise Exception(
            f"This worker can only handle SignedImmediateSyftMessageWithoutReply. {obj_msg}"
        )
