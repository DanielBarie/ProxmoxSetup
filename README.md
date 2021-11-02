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
- The Proxmox installer will overwrite the network configuration.
- Console login, brought up network:
``` 
ip addr add <ip CIDR> dev eno2
ip route add default via <gw address>
``` 
- connected to server, accessed web interface https://<ip>:8006
- did as told, added vmbr0
- networking snafu
- back to console (add eno2 to bridge)
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
``` 
- re-start networking
  ``` 
  systemctl restart networking
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
    
  
  
