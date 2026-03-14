"""
Centralised configuration — all settings read from environment variables.
"""
import os


class Config:
    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    API_KEY = os.getenv("API_KEY", "")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # MySQL
    MYSQL_HOST = os.getenv("MYSQL_HOST", "coastcapital-mysql")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "dbadmin")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "homelab_silver")

    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

    # Local machine (Mac / Docker host) — SSH via host.docker.internal
    LOCAL_HOST = os.getenv("LOCAL_HOST", "host.docker.internal")
    LOCAL_USER = os.getenv("LOCAL_USER", "")           # Mac username (required)
    LOCAL_SSH_KEY = os.getenv("LOCAL_SSH_KEY", "/run/secrets/ssh_key")
    LOCAL_SSH_PASSWORD = os.getenv("LOCAL_SSH_PASSWORD", "")
    LOCAL_MACHINE_NAME = os.getenv("LOCAL_MACHINE_NAME", "Mac")
    LOCAL_MACHINE_DESC = os.getenv("LOCAL_MACHINE_DESC", "Docker Host · macOS")
    MONITOR_LOCAL = os.getenv("MONITOR_LOCAL", "true").lower() == "true"

    # Remote Ubuntu server — SSH
    SERVER_HOST = os.getenv("SERVER_HOST", "")
    SERVER_USER = os.getenv("SERVER_USER", "ubuntu")
    SERVER_SSH_KEY = os.getenv("SERVER_SSH_KEY", "/run/secrets/ssh_key")
    SERVER_SSH_PASSWORD = os.getenv("SERVER_SSH_PASSWORD", "")
    SERVER_NAME = os.getenv("SERVER_NAME", "Ubuntu Server")
    SERVER_DESC = os.getenv("SERVER_DESC", "GPU Server · Ubuntu")

    # Extra machines (JSON array for growth beyond Mac + Ubuntu)
    # Format: [{"name":"GPU2","type":"ubuntu","desc":"Second GPU","host":"192.168.1.y",
    #           "user":"ubuntu","ssh_key":"/run/secrets/ssh_key2","ssh_password":""}]
    EXTRA_MACHINES = os.getenv("EXTRA_MACHINES", "")

    # UniFi
    UNIFI_HOST = os.getenv("UNIFI_HOST", "")
    UNIFI_USERNAME = os.getenv("UNIFI_USERNAME", "")
    UNIFI_PASSWORD = os.getenv("UNIFI_PASSWORD", "")
    UNIFI_SITE = os.getenv("UNIFI_SITE", "default")
    UNIFI_PORT = int(os.getenv("UNIFI_PORT", "443"))

    # Plex
    PLEX_URL = os.getenv("PLEX_URL", "")
    PLEX_TOKEN = os.getenv("PLEX_TOKEN", "")

    # Home Assistant
    HA_URL = os.getenv("HA_URL", "")
    HA_TOKEN = os.getenv("HA_TOKEN", "")

    # Ollama
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

    # CoreDNS — local DNS server
    DNS_HOSTS_FILE = os.getenv("DNS_HOSTS_FILE", "/app/dns/custom.hosts")
    DNS_HEALTH_URL = os.getenv("DNS_HEALTH_URL", "http://homelab-dns:8080/health")
    DNS_UPSTREAM   = os.getenv("DNS_UPSTREAM", "1.1.1.1, 8.8.8.8")

    # Portainer
    PORTAINER_URL = os.getenv("PORTAINER_URL", "")
    PORTAINER_USERNAME = os.getenv("PORTAINER_USERNAME", "")
    PORTAINER_PASSWORD = os.getenv("PORTAINER_PASSWORD", "")

    # Homepage
    HOMEPAGE_URL = os.getenv("HOMEPAGE_URL", "")

    # Timezone
    TIMEZONE = os.getenv("TZ", "America/New_York")
