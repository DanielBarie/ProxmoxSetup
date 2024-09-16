# Using Proxmox to serve GNS3 VMs for a Student Networking Lab.
Our goal is to set up lab environment for students to learn basic network / network management.
We need to do this efficiently because the number of students is quite large. Terraform will be used for duplicating a VM template.

There are some base assumptions:
- Max. number of concurrent students per lab session is approx. 25. (Has proven to work for up to 50 concurrent users after RAM upgrade to 1TB)

And some constraints:
- We work in a computing lab.
- No funding for continuous licensing fees (basically a one-shot lump sum of money that has/had to be spent immediately).
- Lab infrastructure (i.e. Windows Desktop PCs) can/may not be modified (no additional programs/apps).

# Decision based on contraints/available infrastructure
- No hardware-based solution (i.e. cobbling individual nodes (e.g. RasPi even if available)), too much of a hassle for a large number of students.
- Set up Virtualization Server: Proxmox, no licensing fees.
- Serve VMs to students, no installation of programs on local computing lab clients required, VMs can be reached via RDP.
- Run a simulation environment on the VMs (GNS3, several alternatives available which aren't nearly as feature-rich as GNS3).
- Provide a complete desktop environment to students (i.e. including Word Processor), so lab reports may be composed/submitted directly from VMs.
 

# Prerequisites
So I have this nice litte server...
```
lscpu                                                                                               
Architecture:                    x86_64                                                                                 
CPU op-mode(s):                  32-bit, 64-bit                                                                        
Byte Order:                      Little Endian                                                                         
Address sizes:                   43 bits physical, 48 bits virtual                                                      
CPU(s):                          96                                                                                     
On-line CPU(s) list:             0-95                                                                                   
Thread(s) per core:              2                                                                                      
Core(s) per socket:              24                                                                                     
Socket(s):                       2                                                                                      
NUMA node(s):                    2                                                                                      
Vendor ID:                       AuthenticAMD                                                                           
CPU family:                      23                                                                                     
Model:                           49                                                                                     
Model name:                      AMD EPYC 7352 24-Core Processor 
```


# tldr
Started out on PVE7. Proxmox doesn't quite like the server's onboard graphics. X11 won't start and I get stuck on a text mode console with the Proxmox v7 installer.
Had to install a basic Debian Bullseye ISO to get started.
Proceeded along the lines of https://pve.proxmox.com/wiki/Install_Proxmox_VE_on_Debian_11_Bullseye.
Ran into several issues on the way.
System has been upgraded to PVE8. Some hiccups along the way (fixes documented at relevant locations).

# First time setup (PVE7) issues that had to be fixed
## Networking
- The Proxmox installer will overwrite the network configuration.
- Console login, brought up network:
``` 
ip addr add <ip CIDR> dev eno2
ip route add default via <gw address>
``` 
- connected to server, accessed web interface https://<ip>:8006
- did as told, added vmbr0
- networking snafu
- back to console (add eno2 to bridge) in /etc/network/interfaces:
``` 
auto eno2                                                                                                               
iface eno2 inet manual                                                                                                                                                                                                                          
auto vmbr0                                                                                                              
  iface vmbr0 inet static                                                                                                         
  address <ip cidr>                                                                                                
  gateway <ip gw>                                                                                                  
  bridge-ports eno2                                                                                                       
  bridge-stp off                                                                                                          
  bridge-fd 0   
  
# bridge, connecting vms to
# the outside world via NAT
auto vmbr1
  iface vmbr1 inet static
  # we'll take this entire private range and put the bridge at the highest address
  # well, not quite. because wtf we'll be assigned an address from the upper end of the /12 range
  # when dialling in via vpn.
  # this is specific to my location.
  # so take care...
  # as an alternative: we may choose to nat private ip addresses coming into our server...
  address 172.23.255.254/13
  bridge-ports none
  bridge-stp off
  bridge-fd 0
  # activate kernel ip forwarding
  post-up echo 1 > /proc/sys/net/ipv4/ip_forward
  # nat all outgoing connections
  post-up iptables -t nat -A POSTROUTING -s '172.16.0.0/13' -o vmbr0 -j MASQUERADE
  # do NAT/Port Translation for incoming connecction to VMs
  # target ip/port (VM running GNS3) is 172.16.10.1:80
  # source is something coming in to vmbr0 on port 9001 proto tcp
  # rinse, repeat for as many vms as you may have.
  # the only case i'd do this is when the server running the
  # VMs is in a trusted network (e.g. in a lab having its own firewalled subnet)
  # post-up iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 9001 -j DNAT --to 172.16.10.1:80
  #
  # any other placement of the server? get a vpn up and keep the GNS3 VMs in
  # the little walled garden of the Virtualization Host.
  # see setting up a docker host for running the ipsec vpn server
  # we thus provide an authenticated secure connection for entitled users
  # the ip of that container host needs to be assigned statically or
  # by means of a dhcp reservation (this is what we do)
  post-up iptables -t nat -A PREROUTING -i vmbr0 -p udp --dport 500 -j DNAT --to 172.16.2.10:500
  post-up iptables -t nat -A PREROUTING -i vmbr0 -p udp --dport 4500 -j DNAT --to 172.16.2.10:4500
  post-down iptables -t nat -F      
``` 
- re-start networking (this will make all VMs lose connection until they have been RESTARTED!)
  ``` 
  systemctl restart networking
  ``` 
  
- check if all these new rules were accepted:
  `iptables --table nat --list`
  
 - delete a rule (by line number):
  - `iptables --table nat -L --line-numbers` to see the rules and line numbers
  - `iptables -t nat -D PREROUTING <line number>`
  
## ZFS Setup
- Needs to be done manually (since we didn't run the "normal" installation).
- Create ZFS pools for SSDs and HDDs
- Create dataset for VM Image storage:
  - `zfs create storage-ssd/vmdata `
  - `zfs set compression=on storage-ssd/vmdata`
- Set VM image storage location in `/etc/pve/storage.cfg`:
  - Add newly created dataset, make sure it is sparse (else GNS3 VM images will be inflated to full size):
  ```
  zfspool: storage-ssd-vmdata
    pool storage-ssd/vmdata
    content images,rootdir 
    mountpoint /storage-ssd/vmdata
    sparse
    nodes VirtNWLab  
  ```
- Create a directory for backup storage (needs to be directory):
  - Create directory on zfs hdd pool
    ```
    zfs create storage-hdd/backup -o mountpoint=/storage-hdd/backup
    ```
  - Datacenter -> Storage -> Add -> Directory, name it (ID), enter /storage-hdd/backup as directory, add vzdump to contents
  - That location may now be used via Datacenter -> Backup -> Add...
- Fun Fact: The GUI will display the "full" VM disk size. If you need to check the real size:
  ```
  zfs list
  ```
- Create a Dataset for storing ISOs because we don't like the default setting (don't want to fill up the system installation SSD). So we want to store ISOs on the storage-hdd pool:
   - `zfs create -o mountpoint=/var/lib/vz/template/iso storage-hdd/iso`
- ZFS drive kapott?
  - https://forum.proxmox.com/threads/how-do-i-replace-a-hard-drive-in-a-healthy-zfs-raid.64528/

## Prepare Terraforming
- Add Role for Terraform (may do pretty much anything...)
  ```
  pveum role add tf-role -privs \
  VM.Allocate VM.Clone \
  VM.Config.CDROM VM.Config.CPU \
  VM.Config.Cloudinit VM.Config.Disk \
  VM.Config.HWType VM.Config.Memory \
  VM.Config.Network VM.Config.Options \
  VM.Monitor VM.Audit VM.PowerMgmt \
  Datastore.AllocateSpace \
  Datastore.Audit \
  SDN.Use \
  Sys.Audit \
  Sys.Console \
  Sys.Modify \
  Pool.Allocate"
  ```
- Add user `tf-user`:
  ```
  pveum user add tf-user@pve
  ```
- Let newly created user have role:
  ```
  pveum aclmod / -user tf-user@pve -role tf-role
  ```
- create API token (so we may acces the server)
  ```
  pveum user token add tf-user@pve terraform-token --privsep=0
  ```
  Take care to save token ID and value.
- Sidenote: Install Terraform on local machine. Works well in WSL (https://techcommunity.microsoft.com/t5/azure-developer-community-blog/configuring-terraform-on-windows-10-linux-sub-system/ba-p/393845)
- Files required:
  - [main.tf](main.tf): Main terraform file.
  - [vars.tf](vars.tf): Variable declarations for main terraform file.
  - [terraform.tfvars](terraform.tfvars): Contains user id and secret, referenced from vars.tf
 
### Troubleshooting Terraforming
Fixed in above instructions for PVE8: After upgrading to PVE8, terraforming would start but never complete. Basically no disk IO -> nothing happening. All the while, Terraform was happily giving elapsed time statements. Some debugging of the telmate provider (https://registry.terraform.io/providers/Telmate/proxmox/latest/docs) gave ``` HTTP/1.1 403 Permission check failed (/sdn/zones/localnetwork/vmbr1, SDN.Use)```. So if that (new) permission isn't given, no terraforming will actually happen. See https://github.com/Telmate/terraform-provider-proxmox/issues/869 and https://github.com/allenporter/k8s-gitops/issues/1428  
Fixed by adding permission: `SDN.Use` (Datacenter -> Permissions -> Roles)

Fixed in above instructions for PVE8 (instructions don't apply to PVE7 anymore!): Next issue after upgrade to PVE8 was Telmate plugin not handling changed data types: See https://github.com/Telmate/terraform-provider-proxmox/issues/863. Switched to fork by TheGameProfi: https://registry.terraform.io/providers/TheGameProfi/proxmox/2.9.15 Needs some additional permissions in the pve role: `vm.migrate pool.allocate sys.audit sys.console sys.modify` as per https://github.com/Orange-Cyberdefense/GOAD/issues/159   
And finally switched back to the original telmate provider with a later version (3.0.1-rc4).

(to be fixed in conjunction with error below): VMs do get created but terraforming hangs at IP verfication. Turns out, VMs didn't boot (so the first few got created but were stuck in a boot loop -> ip verification failed). Problem was with a boot disk mixup, see https://github.com/Telmate/terraform-provider-proxmox/issues/704

Fixed in main.tf: Error: error updating VM: 500 invalid bootorder: device 'scsi0' does not exist', error status:. We now need to explicitly state the disks that are to be created. Seems like PVE8 implemented some better parameter verfification for boot disk/boot order setting. Included `disks` block in terraform configuration file.


## Add 2FA for admin (i.e. root@pam) account
Click TFA while in the account menu:  
![grafik](https://github.com/DanielBarie/ProxmoxSetup/assets/73287620/b9a616a3-ae9d-4c03-93de-5b11b29d45e6)

Add some recovery codes and the desired second factor:
![grafik](https://github.com/DanielBarie/ProxmoxSetup/assets/73287620/95c2ae9b-e0f9-422c-af7d-63dbef80faaf)



# Fun with VMs
This section is sort of a documentation along the way.  
- First, we tried running GNS3 VM (Compute) images. These were accessed from GUI components installed on the local Windows PCs. We thus failed to achieve one of our main goals (not to install software on the pool PCs). Another issue was the permanent danger of incompatible versions of GUI and VM. Not great. So the Web GUI of the VM was the next logical step. Well, not quite ready, yet.
- I like Ubuntu and there's good documentation for installing GNS3 in a Ubuntu environment. So we chose to have a full desktop environment with GUI and compute (quem) installed in Ubuntu VMs. RDP / VNC won't work as intended. Not such a good idea.
- So much pain later: Debian manual install is a pain. But it finally works (pretty much as intended).
- 
## The GNS3 VM
  - GNS3 provides a KVM image, this is what Proxmox is made for: https://github.com/GNS3/gns3-gui/releases
  - This will give us a Web-UI included with the VM or a way of connecting to the VM via the Windows GUI.
  - Create a nice place to store original images for VMs: `zfs create storage-hdd/originale`
  - Download this to some nice place: `wget https://github.com/GNS3/gns3-gui/releases/download/v2.2.26/GNS3.VM.KVM.2.2.26.zip`
  - Unzip, you'll end up with three files: Two qcow2 disk images and a bash script.
  - Create VM in Proxmox GUI (mostly leaving defaults untouched EXCEPT FOR CPU TYPE which must be set to HOST (else you'd have to disable KVM in the GNS3 VM itself).
  - Note VM number.
  - Import Disks into VM: 
    - `qm importdisk <VM number> GNS3\ VM-disk001.qcow2 storage-ssd-vmdata`
    - `qm importdisk <VM number> GNS3\ VM-disk002.qcow2 storage-ssd-vmdata`
  - Attach these disks to the SATA controller
  - Set boot order to start from the fist disk (Options, Boot Order).
  - Set network interface to be on vmbr1
  - Disable firewall on network interface (checkbox)!
  - Start quemu guest extensions (in GNS VM):
  ```
  sudo apt-get update
  sudo apt-get install qemu-guest-agent
  sudo systemctl start qemu-guest-agent
  ```
  if systemctl doesn't work, do `service qemu-guest-agent start`
  - Set locale `sudo dpkg-reconfigure locales`
  - To fix annoying keyboard: `sudo dpkg-reconfigure keyboard-configuration`, happily overriding previously set defaults. 
  - install useful software: `sudo apt-get install mc nano`
  - set user name / password for web ui in `~/.config/GNS3/<version number>/gns3_server.conf`:
    - `auth = true`
    - `user = <user name>`
    - `password = <password>`
  - reboot: `sudo reboot`
  
  ### Orchestrate Multiple Instances of the GNS3 VM
  We'd love to have multiple instances of the GNS3 VM running at the same time so each student will be able to use a personalized instance. 
  - Create a Master VM with all appliances (Webterm, Kali, CHR,...) installed.
  - Convert it to template (GUI) 
  - Clone it (CLI): `qm clone <id to be cloned> <id of clone>` 
  
  Now, how do we keep these apart and serve a particular instance each time to each student?
  There's some options:
  - Cloud Init for setting IP Adresses. Won't do that because we'd have to install the cloud init stuff on the GNS3 VM. (Can be done, no worries.)
  - Setting IP Adresses via DHCP. When cloning a VM, PVE will randomly assign a MAC address to the clone. So we need to fix that to be able to assign a certain IP to the instance via DHCP.
  
 We'll go for setting IPs via DHCP. Just because I haven't had the time yet to implement cloud init.
 Update: Let's try terraforming...
#### Setting IPs via DHCP.
- Set a known MAC: `qm set <ID> -net0 virtio=xx:xx:xx:xx:xx:xx,bridge=vmbr1`
#### Cloud Init
- What a wonderful idea to be implemented featuring:
  - Individual account settings (username/password) for each VM
  - IP address setting for each VM
  - Generation of ssh keys for each VM
  - Setting locale and keyboard (maybe already set in the template that was used for cloning)
- See below for using it with a complete Ubuntu VM.
  
 
### Made a mistake setting the boot order?
  - For whatever reason you'll end up being unable to shut down the VM (stuck in PXE)
  - `fuser /var/lock/qemu-server/lock-<VM number>.conf`
  - `kill <PID holding the lock>`
  - `qm stop <VM ID>`
  
### Can't connect to a remote instance of GNS3 
- Check if there's a version mismatch between GUI/Controller and the remote VM. The error message is really, really well hidden. Guys, can't you make this a pop up? 
 ![Screenshot with small error message top right](https://github.com/DanielBarie/ProxmoxSetup/blob/main/gns_version_mismatch.png "Error Message") 

## Setting up Ubuntu VM with GNS3 
  - get the image, move it to `/var/lib/vz/template/iso/`
  - This actually is the preferred way.
  - We'll work around the authentication issues and stuff
  - Configure VM:
    - System: 
      - Set QEMU Guest Agent checkbox 
    - Disk:
      - Create a disk (32GB should do)
      - Set storage location to ssd-storage-vmdata pool
      - Do you need a backup? 
    - CPU
      - Set CPU type to host
      - Let it have 2 cores
    - Memory:
      - 4 GB
    - Network
      - Attach to vmbr1
      - Uncheck Firewall
  - Run a VM installation with an Ubuntu image (e.g. 20.04 LTS)
    - Choose minimal install.
    - Add an admin user
    - Later, add student user 
  - Add Guest Extensions:
    ```
    sudo apt-get install qemu-guest-agent
    sudo systemctl start qemu-guest-agent
    ```
  - Add useful programs:
    ```sudo apt-get install mc nano```
  - (Add VNC Server: `sudo apt-get install vino`)
  - (Deactivate VNC Encryption. If not, lots of clients will not work. https://wiki.ubuntuusers.de/VNC/#Authentifizierungsproblem-vino-server
    - `sudo apt-get install dconf-editor`
    - Start dconf-editor, go to "org.gnome.desktop.remote-access" deactivate key "require-encryption")
  - Add Wireshark: `sudo apt-get install wireshark`, make sure you let normal users do packet captures.
  - Add GNS3 as per https://docs.gns3.com/docs/getting-started/installation/linux/
    - Choose to run appliances locally
    - No need to remove docker packages if you've chosen a minimal install.
    - Need to add (new) docker repo and install from it, though.
    - Add openssh: `sudo apt-get install openssh-server`
    - Add VNC viewer for use with GNS3 appliances (e.g. webterm): `sudo apt-get install tigervnc-viewer`
    - Allow remote VNC access: Einstellungen -> Freigabe -> Bildschirmfreigabe (anyway, won't work if user is not already logged in)
    - Add packages for appliances: `sudo apt -y install bridge-utils cpu-checker libvirt-clients libvirt-daemon qemu qemu-kvm`
    - Add student user to relevant groups:
      ```
      sudo usermod -aG ubridge student
      sudo usermod -aG libvirt student
      sudo usermod -aG kvm student
      sudo usermod -aG wireshark student
      sudo usermod -aG docker student  
      ```
    - Install xrdp: `sudo apt-get install xrdp`
      - Reduce bpp in /etc/xrdp.ini
      - Set Auto-Terminate for abandoned/idle sessions, edit `/etc/xrdp/sesman.ini`:
        ```
        KillDisconnected=true
  
        ;; DisconnectedTimeLimit (seconds) - wait before kill disconnected sessions
        ; Type: integer
        ; Default: 0
        ; if KillDisconnected is set to false, this value is ignored
        DisconnectedTimeLimit=0

        ;; IdleTimeLimit (seconds) - wait before disconnect idle sessions
        ; Type: integer
        ; Default: 0
        ; Set to 0 to disable idle disconnection.
        IdleTimeLimit=600
        ```
    - (If you insist on VNC: Activate auto-sign-in for student user (because of vnc issues). Beware: This will break xrdp access. )
    - (Maybe try fixing VNC login via: https://askubuntu.com/questions/1244827/cant-acces-to-xauthority-for-x11vnc-ubuntu-20-04)
    - Prevent Machine Shutdown and Reboot by unprivileged student user:
      - Edit `/etc/polkit-1/localauthority/50-local.d/restrict-login-powermgmt.pkla`
      - Add content to above file:
        ```
        [Disable lightdm PowerMgmt]
        Identity=unix-user:*
        Action= org.freedesktop.login1.power-off;org.freedesktop.login1.power-off-multiple-sessions
        ResultAny=no
        ResultInactive=no
        ResultActive=no 
        [Disable lightdm reboot]
        Identity=unix-user:*
        Action= org.freedesktop.login1.reboot;org.freedesktop.login1.reboot-multiple-sessions
        ResultAny=no
        ResultInactive=no
        ResultActive=no  
        ```
    - Get rid of that stupid color profile authorization warning:
      - create file `sudo touch /etc/polkit-1/localauthority/50-local.d/52-allow-color-manager-create-device.pkla`
      - nano that file, content:
        ```
        [Allow Color Device]
        Identity=unix-user:*
        Action=org.freedesktop.color-manager.settings.modify.system;org.freedesktop.color-manager.create-device
        ResultAny=no
        ResultInactive=no
        ResultActive=yes

        [Allow Color Profile]
        Identity=unix-user:*
        Action=org.freedesktop.color-manager.settings.modify.system;org.freedesktop.color-manager.create-profile
        ResultAny=no
        ResultInactive=no
        ResultActive=yes
        ```
    - Restart polkit: `sudo systemctl restart polkit`
    - No Login via RDP? (Stuck after xrdp green login screen without any error message)
      - `netstat -tlnp`, does xrdp listen on port 3389?
      - probably only on tcp6 3389? I have no words for this... 
        ```
        (Es konnten nicht alle Prozesse identifiziert werden; Informationen über
        nicht-eigene Processe werden nicht angezeigt; Root kann sie anzeigen.)
        Aktive Internetverbindungen (Nur Server)
        Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name
        tcp        0      0 127.0.0.1:631           0.0.0.0:*               LISTEN      -
        tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN      -
        tcp        0      0 192.168.122.1:53        0.0.0.0:*               LISTEN      -
        tcp        0      0 127.0.0.53:53           0.0.0.0:*               LISTEN      -
        tcp6       0      0 ::1:631                 :::*                    LISTEN      -
        tcp6       0      0 :::22                   :::*                    LISTEN      -
        tcp6       0      0 :::3389                 :::*                    LISTEN      -
        tcp6       0      0 ::1:3350                :::*                    LISTEN      -
        ```
      - change `/etc/xrdp/xrdp.ini`
        ```
        ;port 3390
        ;need to change this to be
        port=tcp://:3389
        ```
  - Cloud init?
    - Doc: https://pve.proxmox.com/wiki/Cloud-Init_FAQ
    - In the VM: `sudo apt-get install cloud-init`
    - Hardware Tab of the VM: Add Cloud Init Drive.   
      ![Screenshot for adding Cloud Init Drive](https://github.com/DanielBarie/ProxmoxSetup/blob/main/pve_add_cloudinit_drive.png)
  - Whatever way of setup was chosen (Cloud Init or not): 
    - Convert the VM to template. 
    - Clone it (linked clone!)
    - Use the clones and set individual network parameters: 
      - `qm set <id of clone> --ipconfig0 ip=172.16.12.xx/23,gw=172.16.31.254`
      - Set individual host names.

## Setting up Debian 12
Downside: No simultaneous sessions local/RDP for same user. Must log out locally to access via RDP.
There's some workarounds (https://c-nergy.be/blog/?p=16698). But we only need remote access anyway (serving VMs).
I'm not quite sure why one should insist on using Debian. The setup just sucks (vs. Ubuntu). Really gotta love Debian for making this work.
- Set up VM
  - Set CPU type to host
  - Set QEMU Guest Agent checkbox 
  - attach to vmbr1
- Install Debian
  - Go for expert install (whether graphical or not...): granular control over packages.
  - add student user
  - Packages:
    - openssh-server
    - Xfce
    - bridge-utils
    - cpu-checker
  - Add useful stuff
    - get root (`su`) 
    - `apt-get install mc nano net-tools traceroute nmap whois dnsutils mtr`
  - add non-free repo (dynamips)
    - edit `/etc/apt/sources.list` to include `non-free` (all sections)
    - `apt-get update`
    - `apt-get install dynamips`
  - install docker (https://docs.docker.com/engine/install/debian/#install-using-the-repository)
    -  be root
    - ```
      sudo install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      chmod a+r /etc/apt/keyrings/docker.gpg
      echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
      apt-get update
      apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ```
  - enable automatic security updates
    - get root
    - `apt-get install unattended-upgrades`
    - enable automatic reboot at night if required (do it. do it.)
      - edit /etc/apt/apt.conf.d/50unattended-upgrades:
        - uncomment `Unattended-Upgrade::Automatic-Reboot "false";` and set to true
        - uncomment `Unattended-Upgrade::Automatic-Reboot-WithUsers "true";`
        - uncomment `Unattended-Upgrade::Automatic-Reboot-Time "02:00";`
      - restart: `systemctl restart unattended-upgrades`
      - check for config errors: `journalctl -u unattended-upgrades -xn`
      - make it automatic:
        - `/usr/sbin/dpkg-reconfigure -plow unattended-upgrades`, say yes
  - Do that polkit stuff for color profile device
    - create file `sudo touch /etc/polkit-1/localauthority/50-local.d/52-allow-color-manager-create-device.pkla`
    - nano that file, content:
      ```
      [Allow Color Device]
      Identity=unix-user:*
      Action=org.freedesktop.color-manager.settings.modify.system;org.freedesktop.color-manager.create-device
      ResultAny=no
      ResultInactive=no
      ResultActive=yes

      [Allow Color Profile]
      Identity=unix-user:*
      Action=org.freedesktop.color-manager.settings.modify.system;org.freedesktop.color-manager.create-profile
      ResultAny=no
      ResultInactive=no
      ResultActive=yes
      ```
    - Restart polkit: `sudo systemctl restart polkit`
  - Add RDP
    - `apt-get install xrdp`
  - Install GNS3:
    - (need to modify qemu package name, https://www.gns3.com/community/featured/how-install-gns3-on-debian-12-bookworm)
    - need to add telnet. Hell, console connects just die without an error if telnet is not installed.
    - need to add tigervnc server
      - `sudo apt install -y python3-pip python3-pyqt5 python3-pyqt5.qtsvg python3-pyqt5.qtwebsockets qemu-system-x86 qemu-kvm qemu-utils libvirt-clients libvirt-daemon-system virtinst wireshark xtightvncviewer apt-transport-https ca-certificates curl gnupg2 software-properties-common telnet wget tigervnc-standalone-server tigervnc-viewer busybox-static`
      - with version 2.2.49 (at least somewhere between 2.2.42 and 2.2.49) we need to add `busybox-static` to that list (done above). This also holds true when upgrading GNS3 (e.g. from 2.2.42 to 2.2.49).
    - get (if not yet) root: `su`
    - This is a highly specific VM, we take care our broken packages ourselves, no virtual environment, please: `pip3 install gns3-server  gns3-gui --break-system-packages`
    - Upgrading is done with `pip3 install --upgrade gns3-server  gns3-gui --break-system-packages`
  - Install git:
    -   apt-get install git
  - compile and install ubridge
    - `apt-get install libpcap-dev`
    - `git clone https://github.com/GNS3/ubridge.git`
    - `cd ubridge`
    - `make`
    - `sudo su` (to get the path right (/usr/sbin))`
    - `make install`
  - Install VPCS:
    - GNS3 (2.2.42) is pretty picky regarding VPCS version. It must be greater than 0.6.something but smaller than 0.8.
    - Debian 12 will install 0.5.something which clearly doesn't match the cirteria
    - The GNS3 repo (https://github.com/GNS3/vpcs) has 0.8.2. TF?
    - Need to patch the source (as per https://github.com/GNS3/vpcs/issues/23 and https://github.com/GNS3/vpcs/issues/13)
    - Go to releases: https://github.com/GNS3/vpcs/releases
    - `wget https://github.com/GNS3/vpcs/archive/refs/tags/v0.6.1.tar.gz`
    - `tar xzvf v0.6.1.tar.gz`
    - `cd vpcs-0.6.1`
    - `cd src`
    - `rgetopt='int getopt(int argc, char *const *argv, const char *optstr);'`
    - `sed -i "s/^int getopt.*/$rgetopt/" getopt.h`
    - `sed -i vpcs.h -e 's#pcs vpc\[MAX_NUM_PTHS\];#extern pcs vpc\[MAX_NUM_PTHS\];#g'`
    - `sed -i vpcs.c -e '/^static const char \*ident/a \\npcs vpc[MAX_NUM_PTHS];'`
    - `unset rgetopt`
    - `./mk.sh`
  - auto-start virtual networking (kvm/libvirt)
    - be root
    - `virsh net-autostart default`
    - `virsh net-start default`
    - does it work?
      - `virsh net-list --all`, needs to show active...
      - `ifconfig`, needs to show something like
        ```
        virbr0: flags=4099<UP,BROADCAST,MULTICAST>  mtu 1500
        inet 192.168.122.1  netmask 255.255.255.0  broadcast 192.168.122.255
        ether 52:54:00:89:9b:bd  txqueuelen 1000  (Ethernet)
        RX packets 0  bytes 0 (0.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 0  bytes 0 (0.0 B)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        ```
  - Add student user to groups
    - `su`
    - `sudo su`
    - `usermod -aG libvirt student`
    - `usermod -aG kvm student`
    - `usermod -aG wireshark student`
    - `usermod -aG docker student` 
  - Start / prepare GNS3
    - Start Menu -> Education -> GNS3
    - Disable update checks: (please don't update during our labs)
      - Edit -> Preferences -> General -> Miscellaneous (remove checkmark)
    - Set VPCS path:
      - Edit -> Preferences -> VPCS -> path to compiled executable (i.e. ~/vpcs-0.6.1/src/vpcs)
 - Prevent Shutdown of VM (user rules, will not be overwritten)  
  - ```nano /etc/polkit-1/rules.d/10-admin-shutdown-reboot.rules```
  - insert
    ```
    polkit.addRule(function(action, subject) {
     if (action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-ignore-inhibit" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
         action.id == "org.freedesktop.login1.reboot" ||
         action.id == "org.freedesktop.login1.reboot-ignore-inhibit" ||
         action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
         action.id == "org.freedesktop.login1.set-reboot-parameter" ||
         action.id == "org.freedesktop.login1.set-reboot-to-firmware-setup" ||
         action.id == "org.freedesktop.login1.set-reboot-to-boot-loader-menu" ||
         action.id == "org.freedesktop.login1.set-reboot-to-boot-loader-entry" ||
         action.id == "org.freedesktop.login1.suspend" ||
         action.id == "org.freedesktop.login1.suspend-ignore-inhibit" ||
         action.id == "org.freedesktop.login1.suspend-multiple-sessions" ||
         action.id == "org.freedesktop.login1.hibernate" ||
         action.id == "org.freedesktop.login1.hibernate-ignore-inhibit" ||
         action.id == "org.freedesktop.login1.hibernate-multiple-sessions"
     ) {
         return polkit.Result.AUTH_ADMIN;
     }
    });
    ```
   - save
   - restart polkit: `service polkit restart`
     
 - Push SSH key (generated on local machine) to VM
   - mine is somewhere in my meta directory...
   - Generation via `ssh-keygen -o -a 100 -t ed25519`, save with approriate name (see below)
   - Push to VM template machine (172.16.10.249): `ssh-copy-id -i ~/.ssh/id_vmgns3stud student@172.16.10.249`
   - for future Ansible work...: (jaja, dangerous. same key for root and student user...)
     - in VM:
       - `nano /etc/ssh/sshd_config`
       - set `PermitRootLogin yes`
       - `systemctl reload sshd`
     - on local admin machine
       - `ssh-copy-id -i ~/.ssh/id_vmgns3stud root@172.16.10.249`
     - in VM:
       - `nano /etc/ssh/sshd_config`
       - set `PermitRootLogin prohibit-password`
       - `systemctl reload sshd`
   - Lazy, don't like typing, so we modify the local (admin computer) ssh config
     - `nano ~/.ssh/config/`
     - assuming all VMs will be in the 172.16.10.2xx-range, add to file:
       ```
       Host 172.16.10.2??
       User student
       IdentityFile ~/.ssh/id_vmgns3stud
       IdentitiesOnly yes
       ```
  - Give clones individual SSH host keys (else will be identical..., check with `ssh-keyscan host | ssh-keygen -lf -`)
    - delete host keys of template vm
    - TODO (run one-shot service at first vm clone startup which will generate new host keys)
  - Add Wireshark Packet Capture Reference File
  - Include local language for spellchecking in LibreOffice

## Terraforming...
- make sure VM has a cloud init drive
- Create Clone of VM
- Convert to template
- wite terraform files (adjust names as per lab)
- `terraform init`
- `terraform plan`
- `terraform apply`
  
## Mikrotik CHR Setup
  - Get current image: `https://download.mikrotik.com/routeros/6.48.5/chr-6.48.5.img.zip`
  - Unzip
  - Convert to qcow2: `qemu-img convert -f raw -O qcow2 chr-6.48.5.img chr-6.48.5-disk-1.qcow2`
  - Import Image: `qm importdisk <VM ID> chr-6.48.5-disk-1.qcow2 storage-ssd-vmdata`
  - Set network interface to be on vmbr1
  - Disable firewall on network interface!
  - Secure it /set it up: (VM running containers will get a fixed dhcp lease)
  ```
  user set admin password=<password>
  ip service disable telnet,ftp,www,api,api-ssl,winbox
  tool mac-server set allowed-interface-list=none
  tool mac-server mac-winbox set allowed-interface-list=none
  tool mac-server ping set enabled=no
  tool bandwidth-server set enabled=no
  ip neighbor discovery-settings set discover-interface-list=none 
  ip dns set allow-remote-requests=no
  ip proxy set enabled=no
  ip socks set enabled=no
  ip upnp set enabled=no
  ip dns set servers=9.9.9.9,8.8.8.8
  ip address add address=172.16.0.1/13 interface=ether1
  ip dhcp-server network add address=172.16.0.0/13 dns-server=9.9.9.9
  ip dhcp-server network set gateway=172.23.255.254
  ip route add gateway=172.16.31.254
  ip pool add name=GNSVMPool range=172.16.10.1-172.16.10.250
  ip pool add name=KaliPool range=172.16.11.10-172.16.11.200
  ip pool add name=UtilServer range=172.16.2.10-172.16.2.200
  ip dhcp-server lease add mac-address=BA:C0:4C:1D:24:73 address=172.16.2.10
  ip dhcp-server add address-pool=GNSVMPool disabled=no name=dhcpS1 interface=ether1
  ```
  
# Setting Up Container Based (LXC) Proxy
These are generic non-Proxmox:
  - https://blog.bj13.us/2016/04/08/roll-your-own-http-proxy-with-squid-alpine-and-lxc.html
  - https://archives.flockport.com/new-micro-containers-based-on-alpine-linux/

 This one is for Proxmox (much better..):
  - https://pve.proxmox.com/pve-docs/chapter-pct.html

## Alpine Linux Base Image
  - `apk add squid`
  - `apk add dansguardian`
  - `apk add nano`
  - `apk add mc`
  - `apk add openrc --no-cache`
  - Configuration roughly according to https://wiki.ubuntuusers.de/Inhaltsfilter/
  - And https://wiki.alpinelinux.org/wiki/Setting_up_Explicit_Squid_Proxy
  
  

  
# DockerRunner VM for running containers
## VPN Server Container
Since the virtualization host is most probably not in a firewalled lab 
but accessible from within a larger part of the network we need some way of protecting the
GNS3 VMs (or else...).
So we make a Debian VM for running Docker which in turn will run a container 
providing the VPN server (and whatnot else...).
- `apt-get install unattended-upgrades`
- `apt-get install docker-compose`
See https://github.com/hwdsl2/docker-ipsec-vpn-server for the container instructions.
- have a nice `env` file:
  ```
  VPN_IPSEC_PSK=<lab psk>
  VPN_USER=<lab user>
  VPN_PASSWORD=<lab password>  
  # private dns so we may access gitlab server etc...
  VPN_DNS_SRV1=172.16.2.10
  # backup dns if our (private) dns fails
  VPN_DNS_SRV2=9.9.9.9
  ```
- start container:
  ```
  docker run \
    --name ipsec-vpn-server \
    --env-file ./vpn.env \
    --restart=always \
    -v ikev2-vpn-data:/etc/ipsec.d \
    -p 500:500/udp \
    -p 4500:4500/udp \
    -d --privileged \
    hwdsl2/ipsec-vpn-server
  ```
- We need to make some modifications to that baseline config to let the clients see our internal servers/VMs:
  - Take only a part of 172.16.0.0/16 subnet as being private (because of VPN dial-in IPs, special to my place, you might have to adapt this).
    - get shell to change `run.sh` inside container:  `docker exec -it ipsec-vpn-server env TERM=xterm bash -l`
      ``` 
      #virtual-private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/12,%v4:!$L2TP_NET,%v4:!$XAUTH_NET
      virtual-private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/13,%v4:!$L2TP_NET,%v4:!$XAUTH_NET 
      ```
- re-start container: `docker restart ipsec-vpn-server`
### Troubleshooting the VPN
You may run into issues with Windows being unable to connect to the VPN server despite having set up forwarding of ports upd:500 and udp:4500 on the Proxmox host:
- Check if packets arrive on the VM running the docker container: `tcpdump -i any port 500` and `tcpdump -i any port 4500`
- If these show packets and there's no connection from Windows: https://github.com/hwdsl2/setup-ipsec-vpn/blob/master/docs/clients.md#windows-error-809
- Or better: Switch to  IKEv2: https://github.com/hwdsl2/docker-ipsec-vpn-server#configure-and-use-ikev2-vpn
  - Downside: Needs Admin Elevation on Windows for certificate import (but so does fixing the double NAT issue for the traditional VPN).
  - Change Server Address: 
    - get shell inside container: `docker exec -it ipsec-vpn-server env TERM=xterm bash -l`
    - get helper script: `wget https://get.vpnsetup.net/ikev2 -O /opt/src/ikev2.sh`
    - getting helper script doesn't work because of name resolution issues: add another DNS to `/etc/resolv.conf`:
      - `vi /etc/resolv.conf` (no nano installed, no apk for installing it without DNS...)
      - `a`, insert new line for new name server
      - `ESC`,`:wq`
      - while we're at it: `apk nano`
    - make helper script executable: `chmod a+x ikev2.sh`
    - run it: `./ikev2.sh`, change to _private_ ip of the server running the VMs (PVE). (Port forwarding for VPN to the VM running the docker container needs to be implemented as per above).
      
### Wishlist
- IKEv2 for better handling of double NAT (works if required, see above).
- Bind mount of env file (no need to re-create the container after changing it)
- Use Dockerfile to build it ourselves:
  - include nano
  - change run.sh:
    - set public IP to our (very specific) private IP of the server running PVE (change `public_ip=${VPN_PUBLIC_IP:-''}`, not just if auo discovery fails)
    - change also needs to be made to ikev2setup.sh
    - change `virtual-private` according to our needs  
- Multiple user support with separate subnets for each
  

# Gitlab Server for providing lab instructions
- First, my idea was setting it up in a Linux Container. First ideas rarely work.
  - According to https://about.gitlab.com/install/#debian
  - Set up Linux Container with Debian base image in Proxmox (I've used v11).
  - When installing the Gitlab package, I set `EXTERNAL_URL="http://versuchsanleitungen.labor"` 
  - Loads of errors during installation related to permissions. 
  - Me being me: I don't have the time to fix this. Let's try something else.
- There's a pre-packaged docker container ready for installation:
  - https://docs.gitlab.com/ee/install/docker.html
  - There already is a VM in Proxmox set up for running docker containers (dockerrunner, see above)
  - So let's give this a shot.
  - Little hiccup when installing docker-compose (somehow the new(er) packages of docker were uninstalled, old ones were installed) was fixed by re-installing docker according to https://docs.docker.com/engine/install/debian/
  - Decided that docker-compose was unnecessary.
  - We'd rather do it traditionally. So we create a bash file for starting the container:
    - `export GITLAB_HOME=/srv/gitlab`
    - `mkdir /srv/gitlab`
    - `nano run-docker-gitlab.sh` in some convenient place
      - re-map ssh port from standard 22 to 2224 since there's other services running on the host using 22
      - re-start container whenever it was stopped (don't want to do this manually just because the server rebooted when applying security updates)
      - map directories to previously created location at `/srv/gitlab`
      - increase (shm-size) space reserved for status information
      ```
       docker run --detach \
          --hostname versuchsanleitungen.labor \
          --publish 443:443 --publish 80:80 --publish 2224:22 \
          --name gitlab \
          --restart always \
          --volume $GITLAB_HOME/config:/etc/gitlab \
          --volume $GITLAB_HOME/logs:/var/log/gitlab \
          --volume $GITLAB_HOME/data:/var/opt/gitlab \
          --shm-size 256m \
            gitlab/gitlab-ee:latest         
         ```
    - `chmod a+x run-docker-gitlab.sh`
    - get it going: `./run-docker-gitlab.sh`
    - takes a while to start up
    - root (=admin) password may be found at `/srv/gitlab/config/inial_root_password` (see https://docs.gitlab.com/omnibus/installation/index.html#set-up-the-initial-password)
    - Do some setup work:
      - Restrict user sign-ups to local domain (dhge.de)
      - Add Terms of use: Make it clear that anything stored here will be deleted on a regular basis.
      - Disable statistics (Admin Area -> Settings -> Metrics and Profiling) to avoid running out of space.
    - set up email for notifications/sign-up confirmations: https://docs.gitlab.com/omnibus/settings/smtp.html
      - the local exchange server is pretty stupid. So this is easy:
      - `nano /srv/gitlab/config/gitlab.rb`
        ```
        gitlab_rails['smtp_enable'] = true
        gitlab_rails['smtp_address'] = "<look up mx record>"
        gitlab_rails['smtp_port'] = 25
        gitlab_rails['smtp_domain'] = "<real domain>"
        gitlab_rails['gitlab_email_enabled'] = true
        gitlab_rails['gitlab_email_from'] = 'labor_rechnernetze_noreply@<real domain>'
        gitlab_rails['gitlab_email_display_name'] = 'Gitlab Server Labor Rechnernetze'
        gitlab_rails['gitlab_email_reply_to'] = '<maybe your mail address>'
        ```
      - re-start container: `docker restart gitlab`
  
# Docker Container running dnsmasq 
This one is for our local DNS resolution so we may have a fake TLD (labor) and various hosts.
https://github.com/jpillora/docker-dnsmasq and https://github.com/DrPsychick/docker-dnsmasq (health check)
- create a nice directory to work in 
- get necessary file (lazy, don't clone repo): 
  - create Dockerfile:
    ```
    ARG ALPINE_VERSION=edge
    FROM alpine:$ALPINE_VERSION
    RUN apk --no-cache add dnsmasq
    # for development/changes to files inside container
    RUN apk --no-cache add nano
    COPY healthcheck.sh /
    RUN chmod +x /healthcheck.sh
    # cannot do this with hosts file because it will be maintained by docker daemon
    # would be too easy
    # we instead have to rely on options in dnsmasq.conf for settung specific hosts
    #COPY hosts /etc/hosts
    #get prepared dnsmasq config file
    COPY dnsmasq.conf /etc/dnsmasq.conf
    # We only do DNS, no DHCP.
    EXPOSE 53 53/udp
    HEALTHCHECK --interval=10s --timeout=3s CMD /healthcheck.sh
    # do environment modifications before starting the dnsmasq service
    # https://stackoverflow.com/questions/38302867/how-to-update-etc-hosts-file-in-docker-image-during-docker-build
    # dooh. we don't use docker-compose.
    # dooh. entry point line modification:
    # can't put it at the end of the entrypoint line (because that will be handed to dnsmasq as an argument)
    # can't put it at the beginning because file does not (yet?) exist
    #ENTRYPOINT ["echo 172.16.2.10  versuchsanleitungen.labor >> /etc/hosts", "/envreplace.sh"]
    #ENTRYPOINT ["/envreplace.sh"]
    ENTRYPOINT ["dnsmasq"]
    # we're running in the foreground (non-daemon)
    CMD ["-k", "--log-facility=-"]
    ```
  - create dnsmasq.conf:
    ```
    #log all dns queries
    log-queries
    #dont use hosts nameservers
    no-resolv
    #use cloudflare/quad9 as default nameservers,
    server=9.9.9.9
    server=1.1.1.1
    strict-order
    #explicitly define host-ip mappings
    # this is our gitlab server hosting lab instructions
    address=/versuchsanleitungen.labor/172.16.2.10
    #define local network
    local=/labor/172.16.in-addr.arpa/
    ```
- `docker build -t dbarie/dnsmasq .`
- run it: `docker run -d --cap-add NET_ADMIN --env-file default.env --restart always --publish 53:53 --publish 53:53/udp  --name dnsmasq-1 dbarie/dnsmasq:latest -k -q --log-facility=-`
- kill it: `docker kill dnsmasq-1`
- remove it (if you want to run a new instance with the same name): `docker rm dnsmasq-1`
  

# Secure SSH Login with second factor (TOTP) in addition to password
  - LEAVE AN EXISTING SSH SESSION OPEN (so as not to lock out yourself)
  - Test login functionality by opening another session!
  - Install pam `sudo apt install libpam-google-authenticator`
  - User to be authenticated must run `google-authenticator`
  - this one is a good one: https://unix.stackexchange.com/questions/513011/sshd-denies-access-with-password-google-authenticator-combo
  - edit `/etc/pam.d/sshd`:
    - add: 
      ``` 
      # Google Authenticator
      auth required pam_google_authenticator.so
      ```
    - maybe append `nullok` to above line to allow users not yet having set up 2FA to continue logging in.
  - edit `/etc/ssh/sshd_config`:
    - change:
      ```
      # Change to yes to enable challenge-response passwords (beware issues with
      # some PAM modules and threads)
      ChallengeResponseAuthentication yes
      ```
    - change:
      ```
      UsePAM yes
      AuthenticationMethods keyboard-interactive
      ```
  - `systemctl restart sshd.service` after having made changes to `/etc/ssh/sshd_config`
    
# GNS3 related stuff
## Tired of uploading huge imaged via the Web UI?
  - ssh into gns3 vm
  - wget the image to `/opt/gns3/images/<subdir according to image type` e.g. `/opt/gns3/images/QEMU` for .qcow2
  - saves so much time :)

## Random communications errors between devices
- Watch out: Run all your appliances on the same VM/Server. Don't mix. 
- Take special care with the docker containers (e.g. webterm). They default to the local VM and won't be able to communicate with appliances running on another VM
- Example: Running a DHCP Server (Mikrotik CHR) on a remote VM, adding an instance of webterm set to DHCP. Webterm won't get a lease. You won't even see DHCP packets on a link when capturing.
 ![Screenshot with appliances on different VMs](https://github.com/DanielBarie/ProxmoxSetup/blob/main/gns3_dockerlocal_othersremote.png "Appliances on different hosts won't communicate.") 
                                                
## Go big or go bust
Get some real guests going
### Ubuntu 20.04 LTS
- The Ubuntu template supplied with the GUI is an old one (v18 LTS). To use a newer one: https://www.gns3.com/marketplace/appliances/ubuntu-cloud-guest
- Be patient when logging in with ubuntu/ubuntu. It will take a while to complete the cloud init for setting username/password.
                                                
           
# ToDo:  
- Give each student a private net (i.e. isolate/firewall VM instances)
- Write ansible playbook for initial VM template config.

# If the only tool you have is a hammer...
## Serving other VMs for Student Labs
### LV
- use xubuntu 24.04 iso in minimal installation
- configure unattended upgrades (automatic reboot)
- install nano, mc
- install openssh
- install / restart (service, not systemctl) qemu-guest-agent
- install cloudinit
- create cloud init drive for vm (proxmox gui)
- install xrdp
- restrict network config:  (attention, polkit has been updated!) (might be overwritten when package(s) get updated)
 - edit `/usr/share/polkit-1/actions/org.freedesktop.NetworkManager.policy`
 - in sections `org.freedesktop.NetworkManager.settings.modify.own`, `org.freedesktop.NetworkManager.network-control`, `org.freedesktop.NetworkManager.enable-disable-network` change setting inside `<allow_active>` to `auth_admin`.
- restrict hibernate:  (might be overwritten when package(s) get updated)
 - edit `/usr/share/polkit-1/actions/org.xfce.power.policy`
 - change settings in section `org.xfce.power.xfce4-pm-helper` to `auth_admin`
- restrict shutdown: (might be overwritten when package(s) get updated)
 - edit `/usr/share/polkit-1/actions/org.xfce.session.policy`
 - change settings in section `org.xfce.session.xfsm-shutdown-helper` to `auth_admin`
- restrict shutdown (user rules, will not be overwritten):
 - ```nano /etc/polkit-1/rules.d/10-admin-shutdown-reboot.rules```
 - insert
   ```
   polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.login1.power-off" ||
        action.id == "org.freedesktop.login1.power-off-ignore-inhibit" ||
        action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
        action.id == "org.freedesktop.login1.reboot" ||
        action.id == "org.freedesktop.login1.reboot-ignore-inhibit" ||
        action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
        action.id == "org.freedesktop.login1.set-reboot-parameter" ||
        action.id == "org.freedesktop.login1.set-reboot-to-firmware-setup" ||
        action.id == "org.freedesktop.login1.set-reboot-to-boot-loader-menu" ||
        action.id == "org.freedesktop.login1.set-reboot-to-boot-loader-entry" ||
        action.id == "org.freedesktop.login1.suspend" ||
        action.id == "org.freedesktop.login1.suspend-ignore-inhibit" ||
        action.id == "org.freedesktop.login1.suspend-multiple-sessions" ||
        action.id == "org.freedesktop.login1.hibernate" ||
        action.id == "org.freedesktop.login1.hibernate-ignore-inhibit" ||
        action.id == "org.freedesktop.login1.hibernate-multiple-sessions"
    ) {
        return polkit.Result.AUTH_ADMIN;
    }
   });
   ```
 - save
 - restart polkit: `service polkit restart`
