#!/usr/bin/env python3

############################################################
# Imports - Imports - Imports - Imports - Imports - Imports
############################################################
# Python provided
import sys
import os
import argparse
import textwrap
import time
import datetime

# Add program modules to the path
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "pymod"))
from output import out
import pakcore as pak
import pakutils

############################################################
# Main - Main - Main - Main - Main - Main - Main - Main
############################################################
rc = 0
progStartTime = time.time()
# Create a generic time stamp we can use throughout the program
timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

################################################
# Command line options
# Create the argparser object
parser = argparse.ArgumentParser(description="Hardware File Package Build Program",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=textwrap.dedent('''

examples:
  > pakbuild manifestfile
  > pakbuild manifestfile -b $EKB_IMAGE_OUT
  > pakbuild manifestfile -o /tmp
'''))

# Required positional args
parser.add_argument('manifestfile', help="The manifest file to use to build the pak.")

# The optional args
parser.add_argument('-b', '--basepath', default=None,
                    help="The base path to look for the manifest data in")
parser.add_argument('-o', '--output', default=None,
                    help="Directory to place output")
parser.add_argument('-n', '--name', default="image",
                    help="The name to give to the output files")
parser.add_argument('-c', '--console-level', default=out.levels.WARN, type=out.levels.argparse, choices=list(out.levels),
                    help="The output level to send to send to the console.  BASE is the default")

# cmdline loaded up, now parse for it and handle what is found
args = parser.parse_args()

# Set the console output level selected
out.setConsoleLevel(args.console_level)

# Here we could optionally setup the expanded logging or just console logging
# For now, leave it disabled and then once we know add it or yank this comment

# Grab our output location and level args right away so we can setup output and logging
# Setup our output directory
# If the user gave us one, use that
# If not, create one in /tmp
if (args.output == None):
    outputPath = os.path.join("/tmp", ("pakbuild-%s" % timestamp))
else:
    outputPath = args.output
# Resolve the full path for output for use throughout
outputPath = os.path.realpath(outputPath)

# Make sure the path exists
if (not os.path.exists(outputPath)):
    # Create the output dir
    try:
        os.mkdir(outputPath)
    except:
        out.critical("The output path does not exist.  Please check the path and re-run")
        out.critical("Problem creating: %s" % outputPath)
        out.critical("Exception: %s" % sys.exc_info()[0])
        sys.exit(1)

# Make sure the user knows where it's all going
out.print("All output going to: %s/%s.*" % (outputPath, args.name))

# Store our filenames
# Put them in a dict should we have additional ouput files besides the output pak
# Also give a way to control the output names
filenames = dict()
filenames['pak'] = os.path.join(outputPath, args.name + ".pak")
filenames['manifest'] = os.path.join(outputPath, args.name + ".manifest")

################################################
# Read in and parse the manifest file

# Get the full path to the file and make sure it exists
manifestFile = os.path.abspath(args.manifestfile)

if (not os.path.exists(manifestFile)):
    out.critical("The given manifest file does not exist!")
    out.critical("Please check the path below and try again")
    out.critical("File given: %s" % manifestFile)
    sys.exit(1)

# Put a message to the screen with the manifest being used
out.print("Manifest file: %s" % manifestFile)
out.moreIndent()

manifest = pak.Manifest()
manifestErrors = manifest.parse(manifestFile)

# If we've accumlated errors, exit here.  A valid manifest is a must
if (manifestErrors):
    out.critical("%d error(s) found parsing the manifest!" % manifestErrors)
    out.critical("Please correct the above errors and run again!")
    sys.exit(manifestErrors)

# Build the full manifest paths and expand directory entries
manifestErrors = manifest.build(args.basepath)

# If we've accumulated errors, exit here.  All the files must exist
if (manifestErrors):
    out.critical("%d error(s) found building the manifest!" % manifestErrors)
    out.critical("Please correct the above errors and run again!")
    sys.exit(manifestErrors)

out.lessIndent()

# Create the archive to load into from the manifest data
out.print("Creating archive")
archive = manifest.createArchive()

out.print("Writing archive")
# All data loaded into the archive, just write it
archive.save(filenames["pak"])

# Write out the now fully built manifest as a reporting of everything in the archive
# It is horribly formatted now, cleanup in the future
with open(filenames["manifest"], 'w') as f:
    print("#!/usr/bin/env python3\n", file=f)
    print(manifest.to_dict(), file=f)

# Print all the output file
out.print("All output in: %s" % outputPath)
out.moreIndent()
out.print("Manifest: %s" % filenames["manifest"])
out.print("Archive: %s" % filenames["pak"])
out.lessIndent()

# Report on total run time of the program
timePassed = (time.time() - progStartTime)
out.info("Total Run Time: %s" % (pakutils.formatTime(timePassed)))