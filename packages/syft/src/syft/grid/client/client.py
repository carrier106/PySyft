# stdlib
import logging
import sys
import time
from typing import Any
from typing import Dict
from typing import Optional
from typing import Type

# third party
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey
import requests

# relative
from ...core.io.connection import ClientConnection
from ...core.io.location.specific import SpecificLocation
from ...core.io.route import SoloRoute
from ...core.node.common.client import Client
from ...core.node.device.client import DeviceClient
from ...core.node.domain.client import DomainClient
from ...core.node.network.client import NetworkClient
from ...core.node.vm.client import VirtualMachineClient
from .grid_connection import GridHTTPConnection

DEFAULT_PYGRID_PORT = 80
DEFAULT_PYGRID_ADDRESS = f"http://127.0.0.1:{DEFAULT_PYGRID_PORT}"


def connect(
    url: str = DEFAULT_PYGRID_ADDRESS,
    conn_type: Type[ClientConnection] = GridHTTPConnection,
    credentials: Dict = {},
    user_key: Optional[SigningKey] = None,
    client_type: Optional[Client] = DomainClient,
) -> Client:
    # Use Server metadata
    # to build client route
    conn = conn_type(url=url)  # type: ignore
    client_type = client_type

    if credentials:
        metadata, _user_key = conn.login(credentials=credentials)  # type: ignore
        _user_key = SigningKey(_user_key.encode(), encoder=HexEncoder)
    else:
        metadata = conn._get_metadata()  # type: ignore
        if not user_key:
            _user_key = SigningKey.generate()
        else:
            _user_key = user_key

    (
        spec_location,
        name,
        client_id,
    ) = client_type.deserialize_client_metadata_from_node(metadata=metadata)

    # Create a new Solo Route using the selected connection type
    route = SoloRoute(destination=spec_location, connection=conn)

    location_args: Dict[Any, Optional[SpecificLocation]] = {
        NetworkClient: None,
        DomainClient: None,
        DeviceClient: None,
        VirtualMachineClient: None,
    }
    location_args[client_type] = spec_location

    # Create a new client using the selected client type
    node = client_type(
        network=location_args[NetworkClient],
        domain=location_args[DomainClient],
        device=location_args[DeviceClient],
        vm=location_args[VirtualMachineClient],
        name=name,
        routes=[route],
        signing_key=_user_key,
    )

    return node


def login(
    url: str = None,
    port: int = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    conn_type: Type[ClientConnection] = GridHTTPConnection,
    verbose=True,
) -> Client:

    if port is None and not url:  # if url is used, we can ignore port
        raise Exception("You must specify a port.")

    if url is None:
        try:
            url = "http://docker-host:" + str(port)
            requests.get(url)
        except Exception as e:
            url = "http://localhost:" + str(port)

    if verbose:
        sys.stdout.write("Connecting to " + str(url) + "...")

    url += "/api/v1"

    if email is None or password is None:
        credentials = {}
        logging.info(
            "\n\nNo email and password defined in login() - connecting as anonymous user!!!\n"
        )
    else:
        credentials = {"email": email, "password": password}

    metadata = conn_type(url=url)._get_metadata()  # type: ignore

    if metadata.node_type == "Domain":
        client_type = DomainClient
    else:
        client_type = NetworkClient

    # connecting to domain
    node = connect(
        url=url, credentials=credentials, conn_type=conn_type, client_type=client_type
    )

    if verbose:
        # bit of fanciness
        sys.stdout.write(" done! \t Logging into")
        sys.stdout.write(" " + str(node.name) + "... ")
        time.sleep(1)  # ok maybe too fancy... but c'mon don't you want to be fancy?
        print("done!")

    return node
