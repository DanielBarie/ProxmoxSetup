
terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "2.9.11"
    }
  }
}
provider "proxmox" {
  pm_api_url = var.api_url
  pm_api_token_id = var.token_id
  pm_api_token_secret = var.token_secret
  pm_tls_insecure = true
  pm_parallel = 2
  }
resource "proxmox_vm_qemu" "rna2023" {
  name = "rna2023-studvm-${count.index + 1}"
  count = 40
  vmid = count.index+1+600
  target_node = var.proxmox_host
  clone = var.template
  ipconfig0 = "gw=172.23.255.254,ip=172.16.100.${count.index + 101}/13"
  # wäre schön, geht aber nicht, weil das auf zfs nicht hinhaut?
  #full_clone  = "false"
  full_clone = "true"
  agent = 1
  #os_type = "cloud-init"
  cores = 2
  sockets = 1
  cpu = "host"
  memory = 8192
  #scsihw = "virtio-scsi-pci"
  #bootdisk = "scsi0"

  #disk {
  #  slot = 0
  #  size = "G"
  #  type = "scsi"
  #  storage = "storage-ssd-vmdata"
  #  discard = "on"
  #}

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
