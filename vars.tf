variable "proxmox_host" {
    default = "VirtNWLab"
}
variable "template" {
    default = "d12gns3stud-c-of-126"
}
variable "nic" {
    default = "vmbr1"
}
variable "api_url" {
    default = "https://<ip>:8006/api2/json"
}
variable "token_secret" {
}
variable "token_id" {
}
