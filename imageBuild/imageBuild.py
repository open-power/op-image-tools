#!/usr/bin/env python3
# IBM_PROLOG_BEGIN_TAG
# This is an automatically generated prolog.
#
# $Source: public/common/utils/imageProcs/tools/imageBuild.py $
#
# IBM CONFIDENTIAL
#
# EKB Project
#
# COPYRIGHT 2022
# [+] International Business Machines Corp.
#
#
# The source code for this program is not published or otherwise
# divested of its trade secrets, irrespective of what has been
# deposited with the U.S. Copyright Office.
#
# IBM_PROLOG_END_TAG
import sys
import os
import argparse
import textwrap
import subprocess
import ast
import shutil

def readConfigFile(configFile):
    with open(configFile, "r") as f:
        try:
            configData = ast.parse(f.read(), mode="eval")
        except SyntaxError as e:
            print("Syntax error parsing manifest, line %d. Entry: '%s'" %
                    (e.lineno, e.text.strip()),file=sys.stderr)
            sys.exit(1)
        try:
            data = ast.literal_eval(configData)
        except ValueError as e:
            # Get the error data, both the message and location
            exc_type, exc_value, exc_traceback = sys.exc_info()
            # First the error message
            print("%s" % (exc_value),file=sys.stderr)
            # Now get the line number and position
            last_tb = exc_traceback
            while last_tb.tb_next:
                last_tb = last_tb.tb_next
            print("Found at location: line=%d, col=%d" %
                    (last_tb.tb_frame.f_locals["node"].lineno,
                       last_tb.tb_frame.f_locals["node"].col_offset),file=sys.stderr)
            sys.exit(1)
    if not 'image_sections' in data.keys():
        print("Required key 'image_sections' not found in config data",file=sys.stderr)
        sys.exit(1)

    return data

def mergeArchives(sectionName, archiveFileList, baseEntries):
    # Create an empty archive for the section
    mergedArchiveFile = os.path.join(gendir, sectionName+'.pak')
    if os.path.exists(mergedArchiveFile): os.remove(mergedArchiveFile)
    archive = pak.Archive(mergedArchiveFile)

    # Add essential entries
    for (entryName,entryPath) in baseEntries:
        entryData = ''.encode()
        if os.path.exists(entryPath):
            with open(entryPath, "rb") as f:
                entryData = f.read()

        archive.add(entryName, pak.CM.store ,entryData)
    archive.save()

    # Merge archives
    if len(archiveFileList) > 0:
        cmd = "%s merge %s %s" % (pakTool, mergedArchiveFile, ' '.join(archiveFileList))
        resp = subprocess.run(cmd.split())
        if resp.returncode != 0:
            print("ERROR: %s failed with rc %d" % (cmd, resp.returncode))
            exit(1)

    return mergedArchiveFile

def setupRepository(basePath, commit,remote):
    print("basePath: %s" % basePath)
    if not os.path.exists(basePath):
        #Download repo
        print("git repo %s does not exist. Attempting to clone it" % basePath)
        basePath=basePath.rstrip('/')
        (dir,repo_name) = os.path.split(basePath)
        os.makedirs(dir,exist_ok=True)
        os.chdir(dir)
        print("cwd: %s  repo: %s" % (os.getcwd(),repo_name))
        cmd = 'git clone -b %s ssh://gerrit-server/%s %s -o gerrit' % (commit, remote, repo_name)
        print(cmd)
        resp = subprocess.run(cmd.split())
        if resp.returncode != 0:
            print("git clone failed with rc %d" % resp.returncode)
            os.chdir(cwd)
            sys.exit(1)

    if not os.path.exists(os.path.join(basePath,'.git')):
        print("%s is not a git repositry" % basePath,file=sys.stderr)
        sys.exit(1)

    os.chdir(basePath)
    resp = subprocess.run(["git","checkout",commit],stdout=subprocess.PIPE)
    if resp.returncode != 0:
        print("git checkout had returncode %d" % resp.returncode,file=sys.stderr)
        os.chdir(cwd)
        sys.exit(1)

    if 'sbe' in remote:
        cmd='./sbe workon odyssey pnor'
        #cmd='internal/src/test/framework/build-script'
        build_cmd='source env.bash\nmesonwrap setup\nmesonwrap build\n./sbe clean\n./sbe build\n'
        #%s/internal/src/test/framework/build-script\n' % basePath
    elif 'ekb' in remote:
        cmd='./ekb workon'
        build_cmd='rm -Rf ./output/*\n./ekb build\n'
    else:
        print('Unknown remote: %s' % remote,file=sys.stderr)
        os.chdir(cwd)
        sys.exit(1)

    with subprocess.Popen(cmd.split(),stdin=subprocess.PIPE) as proc:
        proc.communicate(input=str.encode(build_cmd))
        if proc.returncode != 0:
            print("Building %s had a returcode %d" % (
                basePath,
                proc.returncode),
                file=sys.stderr)
            os.chdir(cwd)
            sys.exit(1)

def buildPartitionTable(partitions):
    # Write the  partitions file
    partitionsfile = os.path.join(gendir,'partitions')
    with open(partitionsfile,'w') as f:
        print(partitions, file=f)

    # Build part.tbl
    cmd = "%s compile-ptable %s %s/part.tbl" % (
            flashBuildTool,
            partitionsfile,
            gendir)
    #print(cmd)
    resp = subprocess.run(cmd.split())
    if resp.returncode !=0:
        print("falshBuildTool failed to build part.table. rc = %d" % resp.returncode)
        sys.exit(resp.returncode)

    return partitionsfile

def addFiles(sectionName, sectionInfo):
    # if file does NOT exist in archive then
    # create an empty file -
    return

############################################################
# Main - Main - Main - Main - Main - Main - Main - Main
############################################################
# NEW
#  foreach section:
#    if runtime:
#     - smoosh sbe and ekb runtime paks
#     - create part.tbl
#     - add part.tbl
#     if hash
#       -calculate hash if called for
#       -add hash
#  build flash image from all paks
#
# Command line options
imageToolDir = os.path.dirname(sys.argv[0])
parser = argparse.ArgumentParser(description="Build image",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=textwrap.dedent('''

examples:
  > pnorBuild.py ../imageConfigs/ody_pnor_dd1_image_config -o ./image_output -n pnor.bin
'''))

parser.add_argument('configfile', help="The configuration file used to build the image.")
parser.add_argument('-b','--build',action='store_true',
                    help='Download repos (if not found), checkout commit and build it')
parser.add_argument('--ekb',default=None,
                    help='Base path of ekb repository. Default: use value in configfile')
parser.add_argument('--sbe',default=None,
                    help='Base path of sbe repository. Defulat: use value in configfile')
parser.add_argument('-o','--output', default='./image_output',
                    help='output directory. default ./image_output')
parser.add_argument('-n','--name', default='image.bin',
                    help='output image filename. default: image.bin')
args = parser.parse_args()

# process the configuration file and load needed modules whos location is based on
# the configuration
configFile = os.path.abspath(args.configfile)
if(not os.path.exists(configFile)):
    print("The given config file: '%s', does not exist!" % configFile, file=sys.stderr)
    sys.exit(1)

configdir = os.path.dirname(configFile)

config = readConfigFile(configFile)

# Get the architecture that's running.
resp = subprocess.run(["uname","-m"],stdout=subprocess.PIPE)
exe_arch = resp.stdout.decode('utf-8').rstrip()

# Get the target architecture if available
target_arch = os.environ.get("ECMD_ARCH")
if not target_arch:
    target_arch = exe_arch

## ekb base
ekbBase = args.ekb
if not ekbBase:
    ekbBase = config['ekbRoot']

ekbBase = os.path.realpath(os.path.expanduser(ekbBase))
ekbImageDir = "%s/output/images/%s" % (ekbBase, target_arch)

## sbe base
sbeBase = args.sbe
if not sbeBase:
    sbeBase = config['sbeRoot']

sbeBase = os.path.realpath(os.path.expanduser(sbeBase))

sbeBuildDir = os.path.join(sbeBase,'builddir')

imageToolDir = os.path.realpath(os.path.expanduser(imageToolDir))
pakBuildTool    = os.path.join(imageToolDir, 'pakbuild.py')
pakTool         = os.path.join(imageToolDir, 'paktool.py')
flashBuildTool  = os.path.join(imageToolDir, 'flashbuild.py')

# TODO signHashList calls crtSigned Container.sh which resides in gsa cengel user space
#signTool        = os.path.join(sbeBase, 'public/src/build/utils/signHashList')
signTool = os.path.join(imageToolDir,'signHashList')
output    = os.path.abspath(args.output)
imagefile = os.path.join(output,args.name)
gendir = os.path.join(output,'gen')
os.makedirs(gendir,exist_ok=True)

cwd = os.getcwd()
# setup git repos and build - only if --build option specified.
if args.build:
    setupRepository(ekbBase, config['ekbCommit'],'hw/ekb-src')
    setupRepository(sbeBase, config['sbeCommit'],'hw/sbe')
os.chdir(cwd)

sys.path.append("%s/public/common/utils/imageProcs/tools/pymod" % ekbBase)

from output import out
import pakcore as pak

#only print out critical errors. For debug, change CRITICAL to DEBUG
out.setConsoleLevel(out.levels.CRITICAL)

section_info = config['image_sections']

replacement_tags = {
        '%ekbImageDir%' : ekbImageDir,
        '%sbeBuildDir%' : sbeBuildDir,
        '%sbeRoot%'     : sbeBase,
        '%gen%'         : gendir,
}

# Resolve archive paths in image_sections
# Merge archives where more than one exists in an image section
partitions = []
for sectionName, info in section_info.items():
    archives    = []
    baseEntries = []

    # Expand tags
    for arc in info['archives']:
        for key,value in replacement_tags.items():
            arc = arc.replace(key,value)
        archives.append(arc)

    if 'files' in info.keys():
        for (entryName,entryPath) in info['files']:
            for key,value in replacement_tags.items():
                entryPath = entryPath.replace(key,value)
            baseEntries.append((entryName,entryPath))

    # merge archives
    section_info[sectionName]['mergedArchive'] = mergeArchives(sectionName, archives, baseEntries)
    partitions.append((sectionName, info['partition_size']))

# Create partitions file and build partion table
partitionsfile = buildPartitionTable(partitions)

# Add signature/hash to sections that require it
signit = True
for sectionName, info in section_info.items():
    if not info['mergedArchive']:
        continue
    if signit and 'hashpath' in section_info[sectionName].keys():
        hashpath = section_info[sectionName]['hashpath']
        outhash = os.path.join(output, hashpath)
        scratch = os.path.join(output,'scratch')

        os.makedirs(outhash,exist_ok=True)
        os.makedirs(scratch,exist_ok=True)

        cmd = "%s hash %s %s/hash.list" % (pakTool,info['mergedArchive'],outhash)
        resp = subprocess.run(cmd.split())
        if resp.returncode !=0:
            print("pakTool hash failed with rc %d" % resp.returncode)
            sys.exit(resp.returncode)

        cmd = "%s -s %s -i %s/hash.list -o %s -c %s" % (
                signTool,
                scratch,
                outhash,
                outhash,
                info['hashcomp'])

        print(cmd)
        resp = subprocess.run(cmd.split())
        if resp.returncode !=0:
            print("signTool failed with rc %d" % resp.returncode)
            sys.exit(resp.returncode)

        os.chdir(output)
        cmd = "%s add %s/%s.pak %s --method %s" % (
                pakTool,
                gendir,
                sectionName,
                hashpath,
                info['hashmethod'])
        print(cmd)
        resp = subprocess.run(cmd.split())
        os.chdir(cwd)
        if resp.returncode != 0:
            print("pakTool add failed with rc %d" % resp.returncode)
            sys.exit(resp.returncode)


# Create image
cmd = "%s build-image %s %s" % (flashBuildTool, partitionsfile, imagefile)
for sectionName, info  in section_info.items():
    cmd = "%s -p %s=%s" % (cmd, sectionName, info['mergedArchive'])
#print(cmd)
resp = subprocess.run(cmd.split())
if resp.returncode != 0:
    print("flashbuild failed with rc %d" % resp.returncode)
    sys.exit(resp.returncode)







