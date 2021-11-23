# Using Proxmox to serve GNS3 VMs for a Student Networking Lab.

Our goal is to set up a Proxmox Server so as to be able to provide students with indiviual instances of the GNS3 VM. 
We need to do this efficiently because the number of students is quite large. 
So we'll configure one instance of the GNS3 VM with all necessary appliances and create a template thereof.
The template will be used to create clones - one for each student.
These clones may be spun up before the lab session and shut down afterwards.

There are some base assumptions:
- Max. number of concurrent students per lab session is approx. 25.

And some constraints:
- The server location is outside the lab.
- The server is located in a separate IP subnet with other servers.
- Network access to various subnets from the student lab is impossible whereas the server may freely access these.
- Network access to the outside world (i.e. the Internet) from the student lab is only possible via proxy whereas the server may freely access any internet location.
- Access to the VMs shall only be possible during lab hours.


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
Proxmox doesn't quite like the server's onboard graphics. X11 won't start and I get stuck on a text mode console with the Proxmox v7 installer.
Had to install a basic Debian Bullseye ISO to get started.
Proceeded along the lines of https://pve.proxmox.com/wiki/Install_Proxmox_VE_on_Debian_11_Bullseye.
Ran into several issues on the way.

# Issues that had to be fixed
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
  address 172.16.254.254/16
  bridge-ports none
  bridge-stp off
  bridge-fd 0
  # activate kernel ip forwarding
  post-up echo 1 > /proc/sys/net/ipv4/ip_forward
  # nat all outgoing connections 
  post-up iptables -t nat -A POSTROUTING -s '172.16.0.0/16' -o vmbr0 -j MASQUERADE
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
- Fun Fact: The GUI will display the "full" VM disk size. If you need to check the real size:
  ```
  zfs list
  ```
- Create a Dataset for storing ISOs because we don't like the default setting (don't want to fill up the system installation SSD). So we want to store ISOs on the storage-hdd pool:
   - `zfs create -o mountpoint=/var/lib/vz/template/iso storage-hdd/iso`
  
# Fun with VMs
## The GNS3 VM
  - GNS3 provides a KVM image, this is what Proxmox is made for: https://github.com/GNS3/gns3-gui/releases
  - Create a nice place to store original images for VMs: `zfs create storage-hdd/originale`
  - Download this to some nice place: `wget https://github.com/GNS3/gns3-gui/releases/download/v2.2.26/GNS3.VM.KVM.2.2.26.zip`
  - Unzip, you'll end up with three files: Two qcow2 disk images and a bash script.
  - Create VM in Proxmox GUI (mostly leaving defaults untouched EXCEPT FOR CPU TYPE which must be set to HOST (else you'd have to disable KVM in the GNS3 VM itself).
  - Note VM number.
  - Import Disks into VM: 
    - `qm importdisk <VM number> GNS3\ VM-disk001.qcow2 storage-ssd-vmdata`
    - `qm importdisk <VM number> GNS3\ VM-disk002.qcow2 storage-ssd-vmdata`
  - Attach these disks to the SATA controller
  - Set boot order to start from the fist disk.
  - Set network interface to be on vmbr1
  - Disable firewall on network interface (checkbox)!
  - Start quemu guest extensions (in GNS VM):
  ```
  sudo apt-get update
  sudo apt-get install qemu-guest-agent
  sudo systemctl start qemu-guest-agent
  ```
  ### Orchestrate Multiple Instances of the GNS3 VM
  We'd love to have multiple instances of the GNS3 VM running at the same time so each student will be able to use a personalized instance. 
  - Create a Master VM with all appliances (Webterm, Kali, CHR,...) installed.
  - Convert it to template (GUI) 
  - Clone it (CLI): `qm clone <id to be cloned> <id of clone>` 
  
  Now, how do we keep these apart and serve a particular instance each time to each student?
  There's some options:
  - Cloud Init for setting IP Adresses. Won't do that because we'd have to install the cloud init stuff on the GNS3 VM. (Can be done, no worries.)
  - Setting IP Adresses via DHCP. When cloning a VM, PVE will randomly assign a MAC address to the clone. So we need to fix that to be able to assign a certain IP to the instance via DHCP.
  
 We'll go for setting IPs via DHCP.
 #### Setting IPs via DHCP.
- Set a known MAC: `qm set <ID> -net0 virtio=xx:xx:xx:xx:xx:xx,bridge=vmbr1`
  
 
## Made a mistake setting the boot order?
  - For whatever reason you'll end up being unable to shut down the VM (stuck in PXE)
  - `fuser /var/lock/qemu-server/lock-<VM number>.conf`
  - `kill <PID holding the lock>`
  - `qm stop <VM ID>`
  
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
  ip address add address=172.16.0.1/16 interface=ether1
  ip dhcp-server network add address=172.16.0.0/16 dns-server=9.9.9.9
  ip dhcp-server network set gateway=172.16.254.254
  ip route add gateway=172.16.254.254
  ip pool add name=GNSVMPool range=172.16.10.1-172.16.10.250
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
Since the virtualization host is most probably not in a firewalled lab 
but accessible from within a larger part of the network we need some way of protecting the
GNS3 VMs (or else...).
So we make a Debian VM for running Docker which in turn will run a container 
providing the VPN server (and whatnot else...).
See https://github.com/hwdsl2/docker-ipsec-vpn-server for the container instructions.
- have a nice `env` file:
  ```
  VPN_IPSEC_PSK=<lab psk>
  VPN_USER=<lab user>
  VPN_PASSWORD=<lab password>  
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
  - Take the entire 172.16.0.0/16 subnet as being private.
    - get shell to change `run.sh` inside container:  `docker exec -it ipsec-vpn-server env TERM=xterm bash -l
      ``` 
      #virtual-private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/12,%v4:!$L2TP_NET,%v4:!$XAUTH_NET
      virtual-private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/16,%v4:!$L2TP_NET,%v4:!$XAUTH_NET 
      ```
- re-start container: `docker restart ipsec-vpn-server`

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
    
  
  
