#!/usr/bin/env python3 
# parse arguments, execute commands and do system stuff
import argparse, random, subprocess, sys

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


