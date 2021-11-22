#!/usr/bin/env python3
# parse arguments, execute commands and do system stuff
import argparse, random, subprocess, sys


print("Set up lab environment for multiple GNS3 VM instances using Proxmox.\n")
print("This script will create a specified amount of clones from a VM.")
print("The clones will be assigned MAC ascending order, starting at a specified base MAC.");
parser = argparse.ArgumentParser()
parser.add_argument("-n", type=int,
                    help="Number of clones to be created.")
parser.add_argument("-sid", type=int,
                    help="ID of source template to be cloned.")
parser.add_argument("-tid", type=int,
                    help="First ID (target ID) of clones to be assigned.")
parser.add_argument("-smac", type=int,
                    help="TODO: Start MAC Address for incremental assignment of MAC Adresses to clones.")
parser.add_argument("-br", 
                    help="VM Bridge to attach VMs to..")


args=parser.parse_args()

print("Number of instances to be created: ",args.n)
print("Source (i.e. Template) ID: ",args.sid)
print("Source (i.e. Template) ID: ",args.tid)
print("Start MAC Address for Clones: ",args.smac)
print("VM Bridge: ",args.br)


if args.n is None:
	print("Number of clones must be given.")
	sys.exit()
if args.n > 255:
	print ("Max. number of clones is 255. (Else our dead simple MAC address generator will fail.)")
	sys.exit()
if args.sid is None:
	print("Source ID (i.e. template to be cloned) must be given.")
	sys.exit()
if args.tid is None:
	print("Target ID must be given.")
	sys.exit()
if args.smac is None:
	print ("No start MAC Address given. Will generate random start MAC Address with subsequent numbering according to clone IDs.")
if args.br is None:
	print ("No VM Bridge given. Will use vmbr1.")


# check if vm to be cloned exists
print("Checking if ID to be cloned exists. Listing VMs...")
# run qm list on proxmox ve
# so we may get a list of vms available
# the  specified source id must be available
result = subprocess.run(["qm", "list"], capture_output=True, text=True)
if result.stderr:
	print ("Encountered an error:")
	print (result.stderr)
	print ("\nExiting...")
	sys.exit()
print (result.stdout)
# generate list containing lines of output
list_of_vms = result.stdout.split("\n")
#print(split)
# this is not entirely foolprof
# if the specified source id is a part of the name of
# any vm the check will pass.
# TODO: Foolprof this check.
matching = [s for s in list_of_vms if str(args.sid) in s]
if matching:
	print ("Found Source VM:")
	print (matching)
if not matching:
	print("Unable to find source VM. Exiting.")
	sys.exit()


# check if any of the target IDs specified already
# exists. If so, we may not create it.
# TODO: foolproof the check (see above)
print ("\n")
print ("Checking if specified target IDs are available...")
for count in range(0,args.n):
	if any(str(args.tid+count) in s for s in list_of_vms):
		print("Target ID "+str(args.tid+count)+" exists. Unable to create. Exiting.")
		sys.exit()
print ("OK.")

for count in range(1,args.n+1):
	print("Creating clone #", count, " of template.\n")
	# argument for --name needs to be separate argument for subprocess.run
	# new name needs to be compatible with dns naming conventions
	result = subprocess.run(["qm", "clone", str(args.sid), str(args.tid+count-1), "--name", "GNS3-Clone"+str(count)+"-of-SID"+str(args.sid)], capture_output=True, text=True)
	if result.stderr:
		print ("Encountered an error:")
		print (result.stderr)
		print ("\nExiting...")
		sys.exit()
	print (result.stdout)

#generate random mac prefix
if not args.smac:
	print("Generating random prefix for subsequent sequential numbering by TID.\n")
	# see https://github.com/alobbs/macchanger/blob/master/src/mac.c
	# generate empty list (tuples are immutable)
	mac = [None] * 6
	# generate bytes 0-4
	# byte 0 needs to be in line with multicast/unicast specs
	# we pretend to be a burned-in-address
	mac[0] = (random.randrange(255) & 0xfc) & 0b11111101
	mac[1] = random.randrange(255)
	mac[2] = random.randrange(255)
	mac[3] = random.randrange(255)
	mac[4] = random.randrange(255)
	# byte 5 will be set to tid 
	# generate it anyway
	mac[5] = random.randrange(255)
	print ( hex(mac[0])[2:],":",hex(mac[1])[2:],":",hex(mac[2])[2:],":",hex(mac[3])[2:],":",hex(mac[4])[2:],":",hex(mac[5])[2:] )
else:
	#TODO: implement parameter
	print("not implemented. exiting.")
	sys.exit()

# now, start setting mac addresses of newly created clones
macstr = hex(mac[0])[2:].zfill(2)+":"+hex(mac[1])[2:].zfill(2)+":"+hex(mac[2])[2:].zfill(2)+":"+hex(mac[3])[2:].zfill(2)+":"+hex(mac[4])[2:].zfill(2)+":"
# set bridge
if args.br is None:
	vmbr="vmbr1"
else:
	vmbr=args.br
for count in range(1,args.n+1):
	print("Setting MAC Address of Clone #", str(count)+"\n")
	# proxmox qm doesn't accept single-digits in mac addresses.
	# so these need to be zero padded (zfill)	macstr = hex(mac[0])[2:].zfill(2)+":"+hex(mac[1])[2:].zfill(2)+":"+hex(mac[2])[2:].zfill(2)+":"+hex(mac[3])[2:].zfill(2)+":"+hex(mac[4])[2:].zfill(2)+":"
	result = subprocess.run(["qm", "set", str(args.tid+count-1), "-net0", "virtio,macaddr="+macstr+hex(count)[2:].zfill(2)+",bridge="+vmbr], capture_output=True, text=True)
	if result.stderr:
		print ("Encountered an error:")
		print (result.stderr)
		print ("\nExiting...")
		sys.exit()
	print (result.stdout)

# print column of mac addresses so we may paste it 
# somewhere to create a script for the assignment of fixed 
# dhcp leases
for count in range(1,args.n+1):
	print (macstr+hex(count)[2:].zfill(2))

