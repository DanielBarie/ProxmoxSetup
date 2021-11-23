#!/usr/bin/env python3 
# parse arguments, execute commands and do system stuff
import argparse, random, subprocess, sys


def query_yes_no(question, default="no"):
	# thank you, SO
	# https://stackoverflow.com/questions/3041986/apt-command-line-interface-like-yes-no-input/3041990
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")

print ("Bulk destroy a number of VMs...")
print ("Will delete ANY AND ALL IDs in between and including lower and upper boundary ID.")
print ("Use with care.")

parser = argparse.ArgumentParser()
parser.add_argument("-range", 
					default=[0-0],
					dest="range",
					help="Define a range of VM/CT IDs to be deleted. <LowID HighID>",
					type=int,
					nargs=2
					)
args = parser.parse_args()
#print (args.range)
#print (len(args.range))

# quick check if range is valid
if (not args.range is None) and (len(args.range) != 1) and (args.range[1] > args.range[0]):
	print(f'The defined range is {args.range[0]}-{args.range[1]}')
else:
	print (f"Undefined range...Exit.")
	sys.exit()

print ("Getting current list of VMs/CTs...")
result=subprocess.run(["qm","list"],capture_output=True, text=True)
print (result.stdout)

# rough check for specified ids
if not result.stderr:
	list_of_vms = result.stdout.split("\n")
else:
	print ("Unable to get list of VMs / CTs.")
	print (result.stderr)
	sys.exit()

for count in range(args.range[0], args.range[1]+1):
	if any(str(count) in s for s in list_of_vms):
		print("Found ID ",count)

reply = query_yes_no("About to destroy. Do you want to proceed?")
#print (reply)
if reply == False:
	print ("Exiting...")
	sys.exit()

for count in range(args.range[0], args.range[1]+1):
	result = subprocess.run(["qm", "destroy", str(count)], capture_output=True, text=True)
	if result.stderr:
		print(result.stderr)
	else:
		print (result.stdout)
