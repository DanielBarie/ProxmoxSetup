
terraform {
  required_providers {
    proxmox = {
      #source = "telmate/proxmox"
      #version = "2.9.11"
      source = "telmate/proxmox"
      version = "3.0.1-rc4"
      #source = "TheGameProfi/proxmox"
      #version = "2.10.0"
    }
  }
}
provider "proxmox" {
  pm_api_url = var.api_url
  pm_api_token_id = var.token_id
  pm_api_token_secret = var.token_secret
  pm_tls_insecure = true
  pm_parallel = 2
  pm_log_enable = true
  pm_log_file   = "terraform-plugin-proxmox.log"
  pm_debug      = true
  pm_log_levels = {
    _default    = "debug"
    _capturelog = ""
  }
}
resource "proxmox_vm_qemu" "psna-vi-gns3-2024" {
  name = "psna-vi-gns3-2024-studvm-${count.index + 1}"
  count = 41
  #count = 2
  vmid = count.index+1+500
  target_node = var.proxmox_host
  clone = var.template
  ipconfig0 = "gw=172.23.255.254,ip=172.16.200.${count.index + 101}/13"
  # wäre schön, geht aber nicht, weil das auf zfs nicht hinhaut?
  #full_clone  = "false"
  full_clone = "true"
  agent = 1
  #os_type = "cloud-init"
  cores = 2
  sockets = 1
  cpu = "host"
  memory = 8192
  # die beiden folgenden einkommentiert
  scsihw = "virtio-scsi-pci"
  bootdisk = "scsi0"
  #boot = "order=scsi0;ide2"
  boot = "order=scsi0"
  # neuen disks block, weil 
  # das olle disk deprecated ist
  # wir brauchen jetzt auch einen disk(s) block
  # weil sonst das cloud init drive nicht richtig funktioniert
  # und das setzen der boot order fehlschlägt (pve8 hat da  
  # wohl den parameter check verbessert und lässt das nur für
  # existierende disks zu (ohne disk(s) block existiert die bootplatte
  # für pve halt nicht?)
#  disk {
#    slot = 4
#    size = "64G"
#    type = "scsi"
#    storage = "storage-ssd-vmdata"
    #discard = "on"
#  }

    disks {
        scsi {
            scsi0 {
                disk {
                    backup             = false
                    cache              = "none"
                    discard            = true
                    emulatessd         = true
                    size               = 64
                    storage            = "storage-ssd-vmdata"
                }
            }
	   scsi1 {
		cloudinit {
			storage        = "storage-ssd-vmdata"
		}
	   }
        }
        #ide {
        #    ide4 {
                #disk {
                #    backup             = false
                #    cache              = "none"
                #    discard            = true
                    #emulatessd         = true
                #    size               = 4M
                #    storage            = "storage-ssd-vmdata"
                #}
	#	cloudinit {
	#		storage		= "storage-ssd-vmdata"
	#	}
        #    }
        #}

    }
  #network {
  #  model = "virtio"
  #  bridge = var.nic
  #}

  network {
    model = "virtio"
    bridge = "vmbr1"
    # limit to x megabyte per sec
    #rate = 5
    # we don't modify the bridge (keep template's bridge)

  }
  provisioner "local-exec" {
    command = "echo ${self.name}: ${self.default_ipv4_address} >> ipv4list.txt"
  }
}
