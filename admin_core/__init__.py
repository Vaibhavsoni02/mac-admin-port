"""Mac / machine admin analytics core."""

from .collect import collect_all
from .network import collect_network, primary_lan_ip

__all__ = ["collect_all", "collect_network", "primary_lan_ip"]
