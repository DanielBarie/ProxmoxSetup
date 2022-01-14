# Using Proxmox to serve GNS3 VMs for a Student Networking Lab.

Our goal is to set up a Proxmox Server so as to be able to provide students with indiviual instances of the GNS3 VM. 
We need to do this efficiently because the number of students is quite large. 
So we'll configure one instance of the GNS3 VM with all necessary appliances and create a template thereof.
The template will be used to create clones - one for each student.
These clones may be spun up before the lab session and shut down afterwards.

There are some base assumptions:
- Max. number of concurrent students per lab session is approx. 25.

And some constraints:
- The server location is outside the lab (physically and logically (see below)).
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
  # we'll take this entire private range and put the bridge at the highest address
  address 172.16.31.254/12
  bridge-ports none
  bridge-stp off
  bridge-fd 0
  # activate kernel ip forwarding
  post-up echo 1 > /proc/sys/net/ipv4/ip_forward
  # nat all outgoing connections 
  post-up iptables -t nat -A POSTROUTING -s '172.16.0.0/12' -o vmbr0 -j MASQUERADE
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
  - Set boot order to start from the fist disk (Options, Boot Order).
  - Set network interface to be on vmbr1
  - Disable firewall on network interface (checkbox)!
  - Start quemu guest extensions (in GNS VM):
  ```
  sudo apt-get update
  sudo apt-get install qemu-guest-agent
  sudo systemctl start qemu-guest-agent
  ```
  - Set locale `sudo dpkg-reconfigure locales`
  - To fix annoying keyboard: `sudo dpkg-reconfigure keyboard-configuration`, happily overriding previously set defaults. 
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
  
 We'll go for setting IPs via DHCP.
 #### Setting IPs via DHCP.
- Set a known MAC: `qm set <ID> -net0 virtio=xx:xx:xx:xx:xx:xx,bridge=vmbr1`
  
 
## Made a mistake setting the boot order?
  - For whatever reason you'll end up being unable to shut down the VM (stuck in PXE)
  - `fuser /var/lock/qemu-server/lock-<VM number>.conf`
  - `kill <PID holding the lock>`
  - `qm stop <VM ID>`
  
## Can't connect to a remote instance of GNS3 
- Check if there's a version mismatch between GUI/Controller and the remote VM. The error message is really, really well hidden. Guys, can't you make this a pop up? 
 ![Screenshot with small error message top right](https://github.com/DanielBarie/ProxmoxSetup/blob/main/gns_version_mismatch.png "Error Message") 
  
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
  - Take the entire 172.16.0.0/16 subnet as being private.
    - get shell to change `run.sh` inside container:  `docker exec -it ipsec-vpn-server env TERM=xterm bash -l
      ``` 
      #virtual-private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/12,%v4:!$L2TP_NET,%v4:!$XAUTH_NET
      virtual-private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/16,%v4:!$L2TP_NET,%v4:!$XAUTH_NET 
      ```
- re-start container: `docker restart ipsec-vpn-server`

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
                                                
                                                
                                                
                                       

                                                
                                                
                                                
