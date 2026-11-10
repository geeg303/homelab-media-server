# Home Assistant OS in a VM on box (VM RUNNING since Nov 9; waiting for the Wi-Fi adapter)

Decided Nov 8 (user): **HAOS in a KVM virtual machine** with its **own USB Wi-Fi adapter** passed through, because the box is Wi-Fi only and Wi-Fi can't be bridged. The VM joins the home Wi-Fi itself as a normal LAN device (own IP via DHCP), so discovery, mDNS, Matter and add-ons all work.

## Adapter (to buy)
Must be MediaTek **MT7921AU** (driver `mt7921u` + firmware `mediatek/WIFI_*MT7961*` are both in the current HAOS x86-64 build, checked against `operating-system` dev branch, HAOS 18.5):
- **Netgear A8000** (AXE3000, Wi-Fi 6E), or
- **ALFA AWUS036AXML** (MT7921AUN)

Avoid MT7612U adapters (their USB firmware isn't in HAOS) and Realtek 8821CU (driver disabled in HAOS).
Plug it into a **USB 2/3 port away from the drive enclosures**, ideally on a short extension cable; USB 3 enclosures put out 2.4 GHz noise.

**Ordered Nov 8: Netgear Nighthawk A8000 (AXE3000), arrives Tue Nov 10** (Amazon ASIN B0H3QDW25F, third-party listing marked "Generic"). On arrival: `lsusb` must show a Netgear/MediaTek device and the host kernel must bind `mt7921u` before it's passed to the VM; if it shows a different chipset, it's a relabeled unit and goes back.

## VM sizing
2 vCPU, 4 GB RAM, 32 GB disk (qcow2 on `/` root LV, 252 GB free), UEFI (OVMF). Host has 20 threads / 30 GB RAM, `/dev/kvm` present. Autostart on boot.

## Steps (after the migration copies, or at least not during an active copy)
1. 🔧 Host packages: `qemu-kvm libvirt-daemon-system virtinst ovmf` (no bridge, no host network changes).
2. 🔧 Download the HAOS `haos_ova-<ver>.qcow2.xz` from the official GitHub release, verify, unpack to `/var/lib/libvirt/images/haos.qcow2`.
3. ✅ (done differently, see Status) `virt-install --name haos --boot uefi --vcpus 2 --memory 4096 --disk /var/lib/libvirt/images/haos.qcow2,bus=virtio --import --os-variant generic --network none --hostdev <usb vendor:product of the adapter> --graphics none --autostart`
   - `--network none`: the VM's only network is the passed-through Wi-Fi adapter.
4. 👤 First boot: HAOS has no Wi-Fi config yet, so it needs one setup step: either a temporary NAT NIC to reach the HAOS UI and set Wi-Fi in Settings → System → Network, or the HAOS console `ha network update wlan0 --wifi-mode infrastructure --wifi-ssid ...` (Wi-Fi password entered by user, never through chat). Then remove the NAT NIC.
5. 👤 user: DHCP reservation for the adapter's MAC on the UniFi router (like the box's).
6. 🔧 Homepage tile (homeassistant widget, long-lived token from user into `homepage.env`), Uptime Kuma monitor, HAOS built-in backups (to `/scratch` share or later `/data/backups/ha`), GitHub sync of the VM definition (`virsh dumpxml haos`).

## Status (Nov 9, 17:30)
- ✅ Packages: qemu-system-x86, libvirt (no default NAT network: disabled + destroyed), virtinst, ovmf. Installed with `NEEDRESTART_MODE=l` (the first install let needrestart restart systemd-resolved: ~1 min DNS blip, containers untouched).
- ✅ VM `haos`: HAOS 18.4 (sha256 verified; 18.5 stable has no OVA asset yet, HA offers the update in the UI), 2 vCPU, 4 GB, 32 GB qcow2 at `/var/lib/libvirt/images/haos.qcow2`, UEFI, autostart. Definition mirrored to GitHub (`host/libvirt/haos.xml`).
- ⚠️ **Temporary network:** QEMU user-mode NIC via `<qemu:commandline>` (`-netdev user,hostfwd=tcp:0.0.0.0:8123-:80`, virtio-net at pci addr 0x10). libvirt's `passt` backend is blocked by Ubuntu's AppArmor profile (file_mmap denied on /usr/bin/passt), so it isn't used. **HAOS 18 serves Home Assistant on port 80** (guest 8123 only redirects to :80), hence host 8123 → guest 80. HA reachable at `http://192.0.2.242:8123` (LAN/Tailscale) until the adapter is in.
- 👤 Next: user finishes onboarding (creates the owner account) soon, since until then anyone on the LAN could.
- Tue: adapter → `lsusb` check → hostdev passthrough → Wi-Fi set in HAOS (password typed by user) → DHCP reservation → remove the temporary NIC (the qemu:commandline block) → Homepage tile + Kuma monitor + backups.

## Notes
- When the box reboots, automations pause; keep life-safety things (locks, smoke) not dependent on HA.
- Zigbee/Z-Wave/Thread need a separate USB radio stick, also passed through to the VM; decide once devices are known.
