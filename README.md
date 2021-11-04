# ProxmoxSetup
WhatAMess


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
  post-up echo 1 > /proc/sys/net/ipv4/ip_forward
  post-up iptables -t nat -A POSTROUTING -s '172.16.0.0/16' -o vmbr0 -j MASQUERADE
  # do NAT/Port Translation for incoming connecction to VMs
  # target ip/port (VM running GNS3) is 172.16.10.1:80
  # source is something coming in to vmbr0 on port 9001 proto tcp
  # rinse, repeat for as many vms as you may have.
  post-up iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 9001 -j DNAT --to 172.16.10.1:80
  post-down iptables -t nat -F      
``` 
- re-start networking
  ``` 
  systemctl restart networking
  ``` 
  
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
  - Secure it /set it up:
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
  ip pool add name=GNSVMPool range=172.16.1.10-172.16.1.250
  ip dhcp-server add address-pool=GNSVMPool disabled=no name=dhcpS1 interface=ether1
  ```
  
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
    
  
  
