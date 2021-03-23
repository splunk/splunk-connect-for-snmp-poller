import logging

logger = logging.getLogger(__name__)

INVENTORY_COMPONENTS_PER_LINE = 5
SNMP_VERSION_2 = "2c"
SNMP_VERSION_3 = "3"


def should_process_inventory_line(host_from_inventory):
    stripped = host_from_inventory.lstrip()
    return True if stripped and stripped[:1] != "#" else False


def is_valid_number(port, validation):
    try:
        integer_value = int(port)
        return validation(integer_value)
    except ValueError:
        logger.error(f"{port} is not a number")
        return False


def is_valid_port(port):
    up_to_65535 = lambda p: p >= 1 and p <= 65535
    return is_valid_number(port, up_to_65535)


def is_valid_second_quantity(seconds):
    any_positive_number = lambda positive_number: positive_number > 0
    return is_valid_number(seconds, any_positive_number)


def resolve_host(hostname):
    import socket

    try:
        return socket.gethostbyname(hostname) if hostname else False
    except socket.error:
        logger.error(f"Cannot resolve {hostname}")
        return False


def is_valid_host(host):
    host_port = [elem.strip() for elem in host.split(":")]
    length = len(host_port)
    if length == 1:
        return resolve_host(host_port[0])
    elif length == 2:
        return resolve_host(host_port[0]) and is_valid_port(host_port[1])
    else:
        return False


def is_valid_version(version):
    return version == SNMP_VERSION_2 or version == SNMP_VERSION_3


def is_valid_community(community_string):
    return True if community_string.strip() else False


def is_valid_profile(profile):
    return True if profile.strip() else False


def is_valid_inventory_line(line):
    logger.debug(f"Validating [{line}]")
    if not line or not line.strip():
        return False

    components = [component.strip() for component in line.split(",")]
    logger.debug(f"Components: {components}")
    if len(components) != INVENTORY_COMPONENTS_PER_LINE:
        return False

    return (
        is_valid_host(components[0])
        and is_valid_version(components[1])
        and is_valid_community(components[2])
        and is_valid_profile(components[3])
        and is_valid_second_quantity(components[4])
    )
