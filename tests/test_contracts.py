#!/usr/bin/env python3
"""Static contract tests for the OpenWrt/Podkop container profile."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class RuntimeDefaultsTests(unittest.TestCase):
    def test_zapret_and_dns_defaults_are_pinned(self) -> None:
        env = read(".env.example")
        self.assertRegex(env, r"(?m)^ZAPRET_TAG=v1\.0\.6$")
        self.assertRegex(env, r"(?m)^DNS_SERVER=quad9_tls$")

    def test_nftables_and_targeted_youtube_strategies(self) -> None:
        config = read("config.default")
        required_domains = {
            "youtube.com",
            "googlevideo.com",
            "youtubei.googleapis.com",
            "ggpht.com",
            "ytimg.com",
        }

        self.assertRegex(config, r"(?m)^FWTYPE=nftables$")
        self.assertIn("--lua-desync=multidisorder:pos=midsld", config)
        self.assertNotIn("multisplit:pos=10:seqovl=1", config)
        self.assertNotIn("fake_default_tls", config)

        http_profiles = [
            line for line in config.splitlines() if "--filter-tcp=80" in line
        ]
        self.assertEqual(len(http_profiles), 1)
        self.assertIn("--hostlist-domains=", http_profiles[0])

        tcp_profiles = [
            line for line in config.splitlines() if "--filter-tcp=443" in line
        ]
        self.assertEqual(len(tcp_profiles), 1)
        self.assertIn("--hostlist-domains=", tcp_profiles[0])

        quic_profiles = [
            line for line in config.splitlines() if "--filter-udp=443" in line
        ]
        self.assertEqual(len(quic_profiles), 1)
        self.assertIn("--hostlist-domains=", quic_profiles[0])

        for profile in (http_profiles[0], tcp_profiles[0], quic_profiles[0]):
            match = re.search(r"--hostlist-domains=([^ ]+)", profile)
            self.assertIsNotNone(match)
            self.assertTrue(required_domains.issubset(set(match.group(1).split(","))))


class ComposeTests(unittest.TestCase):
    def test_bridge_isolation_and_loopback_bindings(self) -> None:
        compose = read("docker-compose.yml")
        self.assertRegex(compose, r"(?m)^    network_mode: bridge$")
        self.assertNotRegex(compose, r"(?m)^    network_mode: host$")
        self.assertNotRegex(compose, r"(?m)^    privileged:")
        self.assertIn("NET_ADMIN", compose)
        self.assertIn(
            '"127.0.0.1:${SOCKS_PORT:-1081}:${SOCKS_PORT:-1081}/tcp"', compose
        )
        self.assertIn(
            '"127.0.0.1:${SOCKS_PORT:-1081}:${SOCKS_PORT:-1081}/udp"', compose
        )
        self.assertIn("DNS_SERVER: ${DNS_SERVER:-quad9_tls}", compose)

    def test_healthcheck_uses_local_runtime_state(self) -> None:
        compose = read("docker-compose.yml")
        healthcheck = read("healthcheck.sh")

        self.assertIn('["CMD", "/opt/healthcheck.sh"]', compose)
        for process in ("sslocal", "ssserver", "nfqws2"):
            self.assertIn(process, healthcheck)
        self.assertIn("INIT_APPLY_FW", healthcheck)
        self.assertIn('nft list table inet "$nft_table"', healthcheck)
        self.assertIn("queue_num", healthcheck)
        self.assertNotIn("SOCKS_PORT", healthcheck)
        self.assertNotRegex(healthcheck, r"\b(nc|curl|wget)\b")
        self.assertNotRegex(healthcheck, r"https?://")


class ImageBuildTests(unittest.TestCase):
    def test_official_shadowsocks_release_is_pinned_and_verified(self) -> None:
        dockerfile = read("Dockerfile")
        self.assertIn("ARG SHADOWSOCKS_VERSION=1.21.2", dockerfile)
        self.assertIn(
            "ARG SHADOWSOCKS_AMD64_SHA256="
            "53e6cc209ab9f925e5a59c9f43d75b8179551fc9e608846d7649b5e3aff22c16",
            dockerfile,
        )
        self.assertIn(
            "ARG SHADOWSOCKS_ARM64_SHA256="
            "19e11f39a1b1cd6f843d2d1b5e7759d557448bc82017ff87b9cfaeeff9814f8f",
            dockerfile,
        )
        self.assertIn('"x86_64-unknown-linux-musl"', dockerfile)
        self.assertIn('"aarch64-unknown-linux-musl"', dockerfile)
        self.assertIn("releases/download/v${SHADOWSOCKS_VERSION}", dockerfile)
        self.assertIn("sha256sum -c -", dockerfile)
        self.assertNotIn("shadowsocks-rust-sslocal", dockerfile)
        self.assertNotIn("shadowsocks-rust-ssserver", dockerfile)
        self.assertIn("ca-certificates", dockerfile)
        self.assertIn(
            "COPY --from=shadowsocks /usr/local/bin/sslocal /usr/bin/sslocal",
            dockerfile,
        )
        self.assertIn(
            "COPY --from=shadowsocks /usr/local/bin/ssserver /usr/bin/ssserver",
            dockerfile,
        )

    def test_multiarch_workflow_is_preserved(self) -> None:
        workflow = read(".github/workflows/docker-build.yml")
        self.assertIn("platforms: linux/amd64,linux/arm64", workflow)
        self.assertIn("docker/build-push-action@v6", workflow)


if __name__ == "__main__":
    unittest.main()
