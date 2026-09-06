from __future__ import annotations

import grpc
from cloudctl_edge_protocol import edge_control_pb2_grpc as pb_grpc

from .grpc_service import EdgeControlService


class ServerConfigurationError(ValueError):
    pass


def validate_bind(bind: str) -> str:
    host, separator, raw_port = bind.rpartition(":")
    if not separator or not host or not raw_port.isdecimal():
        raise ServerConfigurationError("bind must be HOST:PORT")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ServerConfigurationError("bind port must be between 1 and 65535")
    if port == 65000:
        raise ServerConfigurationError("Edge Hub cannot bind the device service port")
    return bind


def create_server(
    service: EdgeControlService,
    *,
    bind: str,
    server_certificate: bytes,
    server_private_key: bytes,
    client_ca_certificate: bytes,
) -> grpc.aio.Server:
    validate_bind(bind)
    if not all((server_certificate, server_private_key, client_ca_certificate)):
        raise ServerConfigurationError("server identity and client CA are required")
    server = grpc.aio.server(
        options=(
            ("grpc.max_receive_message_length", 4 * 1024 * 1024),
            ("grpc.max_send_message_length", 4 * 1024 * 1024),
        )
    )
    pb_grpc.add_EdgeControlServicer_to_server(service, server)
    credentials = grpc.ssl_server_credentials(
        [(server_private_key, server_certificate)],
        root_certificates=client_ca_certificate,
        require_client_auth=True,
    )
    if server.add_secure_port(bind, credentials) == 0:
        raise ServerConfigurationError(f"could not bind Edge Hub to {bind}")
    return server
