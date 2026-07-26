# Network Documentation — Middle Earth

Disaster-recovery reference for the home network behind the UDM Pro
("Gandalf"). Generated from live controller data, not from memory or
assumption — every section below was pulled directly from the Network
Integration API and UniFi's legacy session API on the date below.

**Snapshot date:** 2026-07-26
**Site:** Middle Earth (internal site id `88f7af54-98f8-306a-a1c7-c9349722b1f6`, legacy short name `default`)
**Controller:** UDM Pro "Gandalf" — UniFi OS console firmware 5.1.19, Network application 10.4.57 (build `atag_10.4.57_34628`, previous `10.3.58`)

## What this document does NOT cover

- **UniFi Protect application settings** — recording resolution/retention,
  motion zones, smart-detection config, Protect users. The Protect app has
  its own separate API; the credentials this document was generated with
  are Network-app-scoped only. What's below for cameras/NVR is
  network-level fact (IP, MAC, firmware, switch port, VLAN) confirmed via
  the client/device records, not Protect's own configuration.
- **Secrets of any kind.** WiFi passphrases, the WAN PPPoE password, and
  the RADIUS shared secret are not retrievable through either API UniFi
  exposes (write-only fields) — they aren't included here because they
  can't be, not because they were deliberately omitted. Retrieve them from
  your password manager during an actual recovery. One token *was*
  available via the API and deliberately excluded: the IPS/IDS signature
  feed license token (`ips.utm_token`) — that's a real credential, not a
  config value, and isn't needed to reconstruct network *topology*.
- **SNMP community string** — SNMP itself is disabled controller-wide, so
  this wasn't considered worth digging into further.

If a full config restore is ever needed, the fastest real path is
restoring from the UDM's own automatic controller backup (Settings >
System > Backups), not manually re-entering everything below. This
document exists for the scenario where that backup is *also* gone, or you
just need to know why something is configured the way it is.

---

## 1. Hardware inventory

| Name | Model | Role | State | IP | MAC | Firmware | Uplinks To |
|---|---|---|---|---|---|---|---|
| Gandalf | UDM Pro | Gateway | ONLINE | 194.164.229.100 (WAN) | f4:92:bf:77:8d:db | 5.1.19 | — |
| Gimli | USW Pro Max 24 PoE | Switch (core) | ONLINE | 192.168.0.201 | f4:e2:c6:ad:97:bd | 7.4.1 | Gandalf |
| Morgoth | USW-Lite-8-PoE | Switch | ONLINE | 192.168.0.204 | ac:8b:a9:40:ac:f1 | 7.4.1 | Gimli |
| Faramir | USW Flex 2.5G 5 | Switch | ONLINE | 192.168.0.208 | 84:78:48:6a:29:16 | 2.1.8 | Gimli |
| Smeagol | USW Flex Mini | Switch | **OFFLINE** (known/intentional) | 192.168.0.203 | f4:92:bf:a3:6d:39 | 2.1.0 | Gimli |
| Boromir | USW Flex Mini | Switch | **OFFLINE** (known/intentional) | 192.168.0.205 | 9c:05:d6:fe:65:21 | 2.1.0 | Morgoth |
| Legolas | U6 Pro | Access Point | ONLINE | 192.168.0.202 | 60:22:32:20:ec:7d | 6.8.2 | Gimli |
| Aragorn | U6 Pro | Access Point | ONLINE | 192.168.0.206 | 9c:05:d6:a7:f4:75 | 6.8.2 | Gimli |

**Topology:** Gandalf (gateway) → Gimli (core switch, 24-port PoE) → everything else fans out from there — Morgoth, Faramir, both APs, and the entire Protect camera set are all wired through Gimli directly. Boromir uplinks through Morgoth rather than Gimli directly.

### UniFi Protect devices (NVR + cameras + chime)

Not visible in the Network app's device list — these are Protect-managed
appliances that appear as network *clients* rather than adopted Network
devices. All confirmed via `product_line: unifi-protect` /
`unifi_device_info_from_ucore` on their client records, not guessed from
naming.

| Name | Model | IP | MAC | Firmware | Switch Port |
|---|---|---|---|---|---|
| Sauron | **UNVR** (NVR appliance) | 192.168.0.207 | e4:38:83:1d:33:83 | 5.1.19 | Gimli #25 |
| garden-left | G4 Bullet | 192.168.40.139 | e4:38:83:0d:2c:8c | UVC.S5L.v5.3.95.67...260612.0521 | Gimli #3 |
| garden-right-garage | G5 Turret Ultra | 192.168.40.207 | 28:70:4e:19:71:e6 | UVC.SAV530q.v5.3.95.67...260612.0645 | Gimli #1 |
| garden-right-kitchen | G5 Turret Ultra | 192.168.40.222 | 28:70:4e:18:ed:eb | UVC.SAV530q.v5.3.95.67...260612.0645 | Gimli #2 |
| doorbell | G4 Doorbell Pro | 192.168.40.157 | f4:e2:c6:0d:a4:69 | UVC.S5L.v5.3.95.67...260612.0521 | Gimli #4 |
| (unnamed) | AI Port | 192.168.40.189 | 1c:0b:8b:da:d1:e8 | aiport4G.mt8390.v5.1.12...260430.0456 | Gimli #6 |
| g6-180 | G6 180 | 192.168.40.224 | 1c:0b:8b:f6:0e:33 | UVC.SAV539gP.v5.3.95.67...260612.0705 | Gimli #7 or #8 (unnamed, Camera VLAN) |
| espressif (Chime PoE) | UniFi Chime | 192.168.40.110 | 28:70:4e:12:38:4f | UP.esp32.v1.7.20.0...240910.0649 | Gimli #5 |

**Notable split:** every actual camera/chime/AI Port sits on the isolated
Camera VLAN (40) via Gimli ports 1–8, but the **NVR itself (Sauron) sits on
the main Default network**, not the Camera VLAN — it needs to reach the
Protect application on the UDM Pro and isn't itself a device being
recorded, so this placement is correct, just worth knowing explicitly
rather than assuming everything Protect-related is on VLAN 40.

---

## 2. WAN / Internet

Dual-WAN, weighted primary + failover-only backup.

| | Internet 1 (primary) | Internet 2 (failover) |
|---|---|---|
| Type | PPPoE | DHCP |
| Load balance | weighted (priority 1) | failover-only (priority 2) |
| PPPoE username | `abb-modem7@aquiss.com` (ISP: Aquiss) — password not retrievable via API | n/a |
| DNS | 1.1.1.1 / 1.0.0.1 (Cloudflare) | 1.1.1.1 / 1.0.0.1 |
| IPv6 | disabled on this WAN | disabled on this WAN |
| Declared bandwidth | 100 Mbps up / 1000 Mbps down | 100 Mbps up / 1000 Mbps down |

Global gateway settings: UPnP disabled, SYN cookies on, ICMP echo-server
health check target `1.1.1.1`, NAT mode `auto`, no VLAN tagging on either
WAN interface.

---

## 3. Networks / VLANs

| Name | Purpose | VLAN | Subnet | DHCP range | DNS/NTP | mDNS |
|---|---|---|---|---|---|---|
| Default | LAN (native/untagged) | — | 192.168.0.0/24 (gw .200) | .6–.254 | 192.168.50.104/.105 (self-hosted Pi-hole) | on |
| IoT | LAN | 30 | 192.168.30.0/24 (gw .1) | .6–.254 | same | on |
| Guest | LAN | 20 | 192.168.20.0/24 (gw .1) | .6–.254 | same | on |
| Camera | LAN | 40 | 192.168.40.0/24 (gw .1) | .6–.254 | same | on |
| VM | LAN | 50 | 192.168.50.0/24 (gw .1) | .6–.99 only (rest reserved for static hosts) | same | on |
| Wireguard | remote-user-vpn | — | 192.168.3.0/24 (gw .1) | .6–.254 (VPN client pool) | pushes same Pi-hole DNS | — |

All five LAN networks share **the same firewall zone** internally (see
§5) — VLAN separation exists at the L2/L3 network level, but zone-wise
they're one "Internal" group. Domain name `home` on all networks. DHCP
lease time 24h everywhere except VM (12h). PXE/netboot is configured on
Default and VM (`netboot.xyz.efi`, boot server `192.168.50.106`) — a
diskless-boot host lives on the VM subnet.

---

## 4. Switch port assignments

Only ports with an override (named or VLAN-pinned) are meaningfully
different from the switch default — full per-port PoE/speed state is
available live via `python3 udmp.py devices`, this table is about
**intent** (what's supposed to be plugged in where), not live link state.

### Gimli (core switch, 24 ports)
| Port | Name | Native Network | PoE | Mode |
|---|---|---|---|---|
| 1–3 | Garden Right Garage / Kitchen / Garden Left | Camera | auto | customize |
| 4 | Doorbell | Camera | auto | customize |
| 5 | Upstairs Door Chime | Camera | auto | customize |
| 6 | AI Port | Camera | auto | customize |
| 7–8 | (unnamed — g6-180 camera + spare) | Camera | auto | customize |
| 9–17, 19–21, 23–24 | (unnamed uplink/trunk ports) | Default | auto/off | all |
| 18 | Denon X3800H AVR | IoT | off | customize |
| 22 | Vicky Work Laptop | Guest | off | customize |
| 25 | Sauron (NVR) | Default | — | all |
| 26 | UDM (uplink to Gandalf) | Default | — | all |

### Morgoth (USW-Lite-8-PoE)
| Port | Name | Native Network | PoE |
|---|---|---|---|
| 1 | Matter/Thread | Camera | auto |
| 2 | Zigbee/Matter/Thread | IoT | auto |
| 3 | PBS | Default | auto |
| 4 | Boromir (downlink) | Default | auto |
| 6 | Alex PC | Default | — |
| 7 | Work Laptop | Guest (isolated: `tagged_vlan_mgmt=block_all`) | — |
| 8 | Uplink to Gimli | Default | — |

### Smeagol (USW Flex Mini, offline)
| Port | Name | Native Network |
|---|---|---|
| 1 | Uplink to Gimli | Default |
| 2 | Jermaine PC | IoT (isolated: `block_all`) |
| 3–5 | (unnamed) | IoT (isolated: `block_all`) |

### Boromir (USW Flex Mini, offline)
| Port | Name | Native Network |
|---|---|---|
| 5 | Vicky Work Laptop | Guest (isolated: `block_all`) |

Both `Work Laptop`/`Vicky Work Laptop` ports use `tagged_vlan_mgmt:
block_all` — that's a **stricter per-port isolation than the Guest SSID
itself currently has** (see §6 finding on `is_guest`), worth noting as the
wired equivalent already does what the wireless side doesn't yet.

---

## 5. Firewall

### Zone structure
Zone IDs have no display-name endpoint exposed by either API (confirmed,
not guessed), so they're referenced here by their last 4 hex characters.
Inferred purpose from which networks/policies reference them:

| Zone (`…suffix`) | Inferred purpose |
|---|---|
| `…fd5f` | Internal — **all five LAN networks** (Default, IoT, Guest, VM, Camera) share this one zone |
| `…fd60` | External/WAN |
| `…fd61` | Gateway itself (referenced by "Block X to GW" rules) |
| `…fd62` | Wireguard VPN |
| `…fd63` | (referenced alongside VPN Users rules; likely a second VPN zone, e.g. site-to-site) |
| `…fd64` | referenced in policy zone set but not tied to a named group directly |

### Firewall groups
| Name | Type | Members |
|---|---|---|
| RFC1918 | address | 192.168.0.0/16, 172.16.0.0/12, 10.0.0.0/8 |
| Pihole | address | 192.168.50.104, 192.168.50.105 |
| NTP Servers | address | 192.168.50.104, 192.168.50.105 |
| HDA Server (Plex) | address | 192.168.50.254 |
| Home Assistant | address | 192.168.0.115 |
| Bastion | address | 192.168.50.103 |
| Hyperion Server | address | 192.168.50.119 |
| Amazon FireTV | address | 192.168.30.82 |
| VPN Users | address | 192.168.10.0/24 |
| UDM Networks (all gateways) | address | 192.168.0.200, .20.1, .30.1, .40.1, .50.1 |
| Block Guest to GWs | address | 192.168.0.200, .30.1, .40.1, .50.1 |
| Block IoT to GWs | address | 192.168.0.200, .20.1, .40.1, .50.1 |
| Block Guest to firewall interface | address | 192.168.20.1 |
| Block IoT to firewall interface | address | 192.168.30.1 |
| Offending ASNs | address | 39 hosting-provider CIDR blocks (manually curated blocklist — DigitalOcean, Choopa/Vultr and similar ranges) |
| DNS | port | 53 |
| NTP Port | port | 123 |
| Plex Port | port | 32400 |
| Plex GDM Ports | port | 32410, 32412–32414 |
| Bastion SSH | port | 32264 |
| MQTT | port | 1883, 1884, 8883, 8884 |
| Hyperion Port | port | 19445 |
| ADB | port | 5555 |
| HTTP, HTTPS, and SSH | port | 80, 8080, 443, 22 |

### Custom policies, in actual priority order

This is a first-match-wins system — lower index evaluates first. The
important structural fact: **`Block Inter-VLAN Routing` (idx 10015) is a
blanket RFC1918↔RFC1918 deny that sits *after* every specific per-service
allow rule below it**, so those allows are genuine, working exceptions to
an otherwise-locked-down inter-VLAN posture, not dead rules.

| Idx | Action | On | Rule | Proto | Source | Destination |
|---|---|---|---|---|---|---|
| 10000 | BLOCK | ✓ | Block ASNs | all | Offending ASNs | Internal |
| 10000 | ALLOW | ✓ | Allow established and related | all | Internal | Internal/VPN/WAN |
| 10000 | ALLOW | ✓ | Allow VPN users to Pihole | all | VPN Users | Pihole |
| 10000 | BLOCK | ✓ | Block Guest to all GW | all | Internal | Block Guest to GWs |
| 10001 | ALLOW | ✓ | Allow main network to all vlans | all | Internal | RFC1918 |
| 10001 | BLOCK | ✓ | Block VPN users to LAN | all | VPN Users | Internal |
| 10001 | BLOCK | ✓ | Block IoT to all GW | all | Internal | Block IoT to GWs |
| 10002 | ALLOW | ✓ | Allow chosen networks / VM to all vlans | all | Internal | RFC1918 |
| 10002 | BLOCK | ✓ | Block IoT to GW web interface and SSH | all | Internal | UDM Networks |
| 10003 | ALLOW | ✓ | Allow chosen networks + Guest to Pihole | all | Internal | Pihole |
| 10003 | BLOCK | ✓ | Block ICMP from IoT to Gateways | icmp | Internal | UDM Networks |
| 10004 | ALLOW | ✗ off | Allow IoT network to Pihole | all | Internal | Pihole |
| 10004 | BLOCK | ✓ | Block Guest to firewall interface | all | Internal | Block Guest to firewall interface |
| 10005 | ALLOW | ✗ off | Allow Camera to Pihole | all | Internal | Pihole |
| 10005 | BLOCK | ✓ | Block IoT to firewall interface | all | Internal | Block IoT to firewall interface |
| 10006 | ALLOW | ✗ off | Allow Guest network to NTP | udp | Internal | NTP Servers |
| 10007 | ALLOW | ✗ off | Allow IoT network to NTP | udp | Internal | NTP Servers |
| 10008 | ALLOW | ✓ | Allow chosen networks + Camera to NTP | udp | Internal | NTP Servers |
| 10009 | ALLOW | ✓ | Allow Plex GDM | udp | Internal | HDA Server |
| 10010 | ALLOW | ✓ | Allow chosen networks + **Guest** to Plex | tcp | Internal | HDA Server |
| 10011 | ALLOW | ✗ off | Allow IoT to Plex | tcp | Internal | HDA Server |
| 10012 | ALLOW | ✓ | Allow IoT to Bastion | all | Internal | Bastion |
| 10013 | ALLOW | ✓ | Allow IoT UDP to Home Assistant | udp | Internal | Home Assistant |
| 10014 | ALLOW | ✓ | MQTT to Home Assistant | all | Internal | Home Assistant |
| **10015** | **BLOCK** | ✓ | **Block Inter-VLAN Routing (the catch-all)** | all | RFC1918 | RFC1918 |
| 10016 | ALLOW | ✓ | Allow VPN users to Pihole | all | VPN Users | Pihole |
| 10016 | BLOCK | ✓ | Block Meross lamp from internet | all | Internal | WAN |
| 10017 | BLOCK | ✓ | Block VPN users to destination LANs | all | VPN Users | Internal |
| 10018–10020 | BLOCK | ✗ off | Block VPN users to IoT/Guest/VM (disabled) | all | VPN Users | Internal |

**Reading guide for recovery:** if rebuilding from scratch, the intent is
clearly "deny inter-VLAN by default, then punch specific service-level
holes." Recreate `Block Inter-VLAN Routing` **last**, after every allow
rule above it, or you'll lock out services that are supposed to work.

---

## 6. Wireless

### Access points
| AP | Model | Uplink | 2.4GHz | 5GHz |
|---|---|---|---|---|
| Legolas | U6 Pro | Gimli (wired) | ch1 / 20MHz | ch153 / 80MHz |
| Aragorn | U6 Pro | Gimli (wired) | ch11 / 20MHz | ch36 / 80MHz |

Both 5GHz channels are non-DFS (UNII-1 and UNII-3) — no radar-triggered
channel changes. No co-channel or adjacent-channel overlap between the
two APs on either band. Both wired-uplinked to the same core switch, not
meshed.

### SSIDs
| SSID | VLAN | Security | WPA3 | PMF | Fast Roaming (802.11v) | Client Isolation | Guest Flag | Hidden |
|---|---|---|---|---|---|---|---|---|
| Mordor | Default (native) | WPA2/WPA3-transition | transition | optional | on | off | off | no |
| Mordor-IOT | 30 (IoT) | WPA2/WPA3-transition | transition | optional | off | off | off | no |
| Mordor-Guest | 20 (Guest) | WPA2/WPA3-transition | transition | optional | on | **off** | **off** | no |
| Mordor-Cams | 40 (Camera) | WPA2/WPA3-transition | transition | optional | off | off | off | **yes** |

**Open finding (previously identified, unresolved as of this snapshot):**
`Mordor-Guest` is not flagged as a UniFi guest network (`is_guest: false`)
and has no client isolation (`l2_isolation: false`) — devices on that SSID
can currently see each other. This does **not** affect the firewall
exceptions in §5 (Guest→Pihole, Guest→Plex) — those operate at L3/VLAN
level, independent of SSID isolation. Fix: enable "Guest Network" on that
WLAN in the UniFi app.

WiFi passphrases are not retrievable via API for any SSID (write-only
field, confirmed — the field simply isn't present in the API response,
not redacted from it) — retrieve from password manager if needed.

---

## 7. VPN

| | Wireguard (remote-user-vpn) | Site-to-site VPN | OpenVPN | IPsec |
|---|---|---|---|---|
| Status | enabled | enabled | not configured (empty) | minimal config present, not actively verified |
| Subnet | 192.168.3.0/24 | — | — | — |
| Local port | 52767 (non-default) | — | — | — |
| Public key | `LBqCfvAOQZljSsgb5O38R8B56HXgRb9Y/9F4WcEf1iA=` | `ufUqk7JpQdPNe2XrAElPifG9KIorkqVTRfxCedrn+gg=` | — | — |
| Remote endpoint | `vpn.modem7.com` | — | — | — |
| DNS pushed to clients | 192.168.50.104/.105 (Pi-hole) | — | — | — |

VPN client traffic (`VPN Users` group, `192.168.10.0/24` — note this is a
**different** subnet from the Wireguard interface's own `192.168.3.0/24`
pool, likely a legacy/different VPN mechanism's client range) is
explicitly blocked from reaching IoT/Guest/VM/general LAN by default
(§5, rules 10001–10017), with Pihole as the one standing exception.
"Teleport" (Ubiquiti's identity-based remote access) is disabled.

---

## 8. Security services

- **IPS/IDS**: mode `ips` (actively blocking, not just detecting).
  Signature categories: the full Emerging Threats / Proofpoint ET open
  set (botcc, malware, exploit, scan, dark-web-blocker-list,
  malicious-hosts, etc. — 30+ categories, all enabled).
- **Honeypot**: enabled, with a decoy host at `.2` on each of
  IoT/Guest/VM/Camera (`192.168.30.2`, `.20.2`, `.50.2`, `.40.2`) — not on
  Default.
- **DNS filtering**: enabled at the platform level but every individual
  network's filter is set to `none` — so no content-category filtering is
  actually active; DNS filtering here is riding on IPS's own detection,
  not a separate blocklist. (Pi-hole handles ad/tracker blocking
  separately, outside UniFi's own filtering.)
- **DPI**: enabled, with fingerprinting on.
- **DNS-over-HTTPS**: manual mode, using Cloudflare + Google as upstream.
- **RADIUS**: enabled, standard ports (1812/1813), `configure_whole_network: true` — referenced by the IoT SSID's `radiusprofile_id`. Shared secret not retrievable via API.
- **SNMP**: disabled.
- **Guest portal**: disabled (`portal_enabled: false`) — consistent with §6's isolation finding; the guest network isn't running UniFi's captive-portal flow at all right now.
- **Global switch settings**: RSTP, DHCP snooping on, jumbo frames off, 802.1X port control off.

---

## 9. Clients

**Live count at snapshot time:** 25 connected (19 wired, 6 wireless — all
6 wireless clients were on the IoT SSID, split evenly 3/3 across the two
APs). **137 total known clients** in the controller's history.

### Statically-reserved IPs (39) — the infrastructure that matters most for recovery

| IP | MAC | Name | Network | Type |
|---|---|---|---|---|
| 192.168.0.2 | 02:42:c0:a8:00:02 | Pihole | — | Docker container |
| 192.168.0.3 | 02:42:c0:a8:00:03 | DNSCrypt | — | Docker container |
| 192.168.0.98 | 48:4d:7e:d2:53:bc | PBS (Proxmox Backup Server) | Default | — |
| 192.168.0.99 | b8:27:eb:ed:3c:a4 | QDevice | — | — |
| 192.168.0.100 | 00:1b:21:3a:17:ec | Alex PC | Default | — |
| 192.168.0.130 | 78:e3:6d:e3:d4:cb | SLZB-06M-Thread | IoT | Zigbee/Thread coordinator |
| 192.168.0.144 | 34:cd:b0:2c:10:4c | tado-bridge-x | Default | — |
| 192.168.0.150 | 30:05:5c:60:5e:05 | Brother Printer | Default | — |
| 192.168.0.161 | 32:c2:87:c9:4d:54 | Terraform | Default | — |
| 192.168.0.207 | e4:38:83:1d:33:83 | Sauron | Default | **UNVR** (see §1) |
| 192.168.0.250 | b4:96:91:40:9c:e2 | Samwise | Default | — |
| 192.168.0.251 | 18:66:da:46:a1:95 | Frodo | Default | — |
| 192.168.0.252 | 00:c0:b7:fb:27:25 | APC UPS | Default | — |
| 192.168.0.253 | 3c:ec:ef:ac:4b:b4 | IPMI | Default | — |
| 192.168.30.6 | 50:c7:bf:5a:ca:c2 | HS100-Router | IoT | Smart plug |
| 192.168.30.7 | c0:06:c3:70:26:9c | KP115-Server | IoT | Smart plug |
| 192.168.30.8 | c0:06:c3:70:25:30 | KP115-Rocket | IoT | Smart plug |
| 192.168.30.10 | 84:f3:eb:80:fb:04 | ESP8266 Weather Station | IoT | — |
| 192.168.30.11 | 44:09:b8:ab:85:04 | Chromecast-Ultra | IoT | — |
| 192.168.30.35 | 5c:62:8b:47:e5:4c | KP115-TV | IoT | Smart plug |
| 192.168.30.45 | 68:9a:87:28:a6:40 | (unnamed) | IoT | — |
| 192.168.30.63 | d0:c9:07:5f:75:ef | Govee Backlight 3 Lite | IoT | — |
| 192.168.30.78 | 8c:a9:6f:35:aa:34 | Denon-AVC-X3800H | IoT | — |
| 192.168.30.81 | 00:06:78:f1:94:f8 | Denon-AVC-X3800H (2nd unit) | IoT | — |
| 192.168.30.82 | e8:4c:4a:cc:bc:8e | Amazon Fire TV | IoT | — |
| 192.168.30.97 | 88:13:bf:5a:d8:f0 | EPLite-Lounge | IoT | — |
| 192.168.30.116 | c8:7b:23:b8:3b:48 | Bose-Smart-Soundbar-600 | IoT | — |
| 192.168.30.118 | a4:e5:7c:f5:bc:3c | Alex-Office-Cololight | IoT | — |
| 192.168.30.132 | a4:e5:7c:f7:66:80 | Ensuite-Cololight | IoT | — |
| 192.168.30.142 | 10:52:1c:6d:78:f4 | awtrix_6d78f4 | IoT | — |
| 192.168.30.144 | 30:68:93:5f:11:17 | P304M-Lounge | IoT | — |
| 192.168.30.148 | d8:0d:17:d8:4c:1f | HS110-BedroomCurtain | IoT | Smart plug |
| 192.168.30.150 | 9c:9c:1f:0c:bc:c4 | awtrix_0cbcc4 | IoT | — |
| 192.168.30.188 | 14:2b:2f:d5:ba:77 | SLZB-06M-Zigbee | IoT | Zigbee coordinator |
| 192.168.30.217 | ea:f6:0a:d2:cc:88 | SLZB-MR1U | IoT | — |
| 192.168.30.226 | 5c:62:8b:47:f1:a8 | KP115-Amp | IoT | Smart plug |
| 192.168.30.229 | 5c:62:8b:47:f3:c4 | KP115-AirFryer | IoT | Smart plug |
| 192.168.30.240 | cc:f7:35:27:80:93 | Firestick | IoT | — |
| 192.168.30.247 | a8:42:a1:df:17:15 | Humidor | IoT | — |

Notable: the two **SLZB coordinators** (`.130` on Default, `.188` Zigbee +
`.217` MR1U on IoT) are Zigbee/Thread/Matter bridge hardware — worth
knowing these are the actual smart-home radio infrastructure, not just
more IoT endpoints, if troubleshooting smart-home connectivity during
recovery.

### VM subnet static hosts (from client records, not the 39 above — these sit above the DHCP pool ceiling of .99)
Referenced throughout §5/§8 by name: Pi-hole/DNS at `.104`/`.105`, HDA
(Plex) server at `.254`, Bastion at `.103`, Home Assistant at `.115`
(actually on Default, not VM — see firewall group), Hyperion at `.119`,
PXE boot server at `.106`, syslog targets at `.114`/`.115`.

---

## Regenerating this document

All data above (except the client-record device-type enrichment in §1/§9,
which used `rest/user`'s richer `unifi_device_info_from_ucore` field
directly, and the IPS/DoH/RADIUS/etc. settings in §8, which aren't wrapped
in a command) can be pulled fresh via the CLI:

```bash
python3 udmp.py sites
python3 udmp.py devices
python3 udmp.py clients
python3 udmp.py radios
python3 udmp.py wlans          # needs UDMP_UI_USERNAME/PASSWORD
python3 udmp.py firewall       # needs UDMP_UI_USERNAME/PASSWORD
python3 udmp.py networks       # needs UDMP_UI_USERNAME/PASSWORD
python3 udmp.py ports          # needs UDMP_UI_USERNAME/PASSWORD
python3 udmp.py known-clients  # needs UDMP_UI_USERNAME/PASSWORD
```

For an interactive, always-current view of the same data without
re-running commands by hand, use the live dashboard
(`python3 docs/dashboard_server.py`, see `README.md`) — its **Save
snapshot** button exports the current rendered state as a standalone
HTML file whenever you need a point-in-time copy, so there's no separate
static-generation step to keep in sync with this file.
