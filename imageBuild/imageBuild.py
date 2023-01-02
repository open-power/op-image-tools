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
    mergedArchiveFile = os.path.join(mergedDir, sectionName+'.pak')
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

    ## Filter out unwanted content - TODO  hopefull in time, this will not be needed.
    if sectionName == 'runtime':
        cmd = "%s remove %s rt/sppe.pak rt/hash.list rt/secure.hdr rt/hwkeyshash.bin" % (pakTool,mergedArchiveFile)
        resp = subprocess.run(cmd.split())
        # Don't care if not found
    if sectionName == 'boot':
        cmd = "%s remove %s boot/hash.list boot/secure.hdr main.fsm" % (pakTool,mergedArchiveFile)
        resp = subprocess.run(cmd.split())
        # Don't care if not_found

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
    if not args.nobranchchange:
        resp = subprocess.run(["git","checkout",commit],stdout=subprocess.PIPE)
        if resp.returncode != 0:
            print("git checkout had returncode %d" % resp.returncode,file=sys.stderr)
            os.chdir(cwd)
            sys.exit(1)
        if args.update:
            if 'sbe' in remote:
                cmd = 'git pull'
                print(cmd)
                resp = subprocess.run(cmd.split())
                if resp.returncode != 0:
                    print("git update failed with rc %d" % resp.returncode)
                    os.chdir(cwd)
                    sys.exit(1) 
            elif 'ekb' in remote:
                cmd = 'git fetch gerrit'
                print(cmd)
                resp = subprocess.run(cmd.split())
                if resp.returncode != 0:
                    print("git update failed with rc %d" % resp.returncode)
                    os.chdir(cwd)
                    sys.exit(1)
                cmd = 'git rebase gerrit/%s' % (commit)
                print(cmd)
                resp = subprocess.run(cmd.split())
                if resp.returncode != 0:
                    print("git update failed with rc %d" % resp.returncode)
                    os.chdir(cwd)
                    sys.exit(1)
            else:
                print('Unknown remote: %s' % remote,file=sys.stderr)
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
        if args.devready:
            if not args.nobranchchange:
                getDevReadyCommits(commit)
            else:
                print("Not getting dev-ready updates because --nobranchchange was specified")
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
    partitionsfile = os.path.join(genDir,'partitions')
    with open(partitionsfile,'w') as f:
        print(partitions, file=f)

    # Build part.tbl
    cmd = "%s compile-ptable %s %s/part.tbl" % (
            flashBuildTool,
            partitionsfile,
            genDir)
    #print(cmd)
    resp = subprocess.run(cmd.split())
    if resp.returncode !=0:
        print("falshBuildTool failed to build part.table. rc = %d" % resp.returncode)
        sys.exit(resp.returncode)

    return partitionsfile

def getDevReadyCommits(commit):
    print("\nRunning ./ekb cronus checkout")
    out, err = subprocess.Popen(['source ./env.bash; ./ekb cronus checkout --branch', commit], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True).communicate()
    # Sometimes seeing stuff in stderr that isn't actually an error, so not going to fail
    if err:
        print("INFO: stderr returned:\n", err)

    print("ekb cronus checkout --branch", commit, "\n")
    print(out)

    # look for explicit problems
    if ('Outstanding tracked changes' or 'Not a git repository' or 'Run this tool from the root' or 'Cherry-picks failed') in out:
        print("ERROR! Failed checking of dev-ready checkouts\n", out)
        os.chdir(cwd)
        sys.exit(1)

    # look for confirmation it worked
    if not ('Checking out' and 'All Cherry-picks applied cleanly') in out:
        print("ERROR! Failed checking out dev-ready checkouts\n", out)
        os.chdir(cwd)
        sys.exit(1)  

    # write output to a file
    filename = os.path.join(output, "cro_image_cronus_checkout.sversion")
    outfile = open(filename, 'w')
    outfile.write(out)
    outfile.close()

def makeHashList(archiveName,hashfile):
    # Create and load the archive
    archive = pak.Archive(archiveName)
    archive.load()

    # Create all the hashes for the selected files
    out.print("Creating hashes")
    out.moreIndent()
    for entry in archive:
       out.print(entry.name)
       entry.hash()
    out.lessIndent()

    #Add the hash.list content
    archive.add(hashfile, pak.CM.store, archive.createHashList())

    # Write the updated archive
    return archive.save()

def saveAndRemove(archiveName, savedArch, extractList):
    archive = pak.Archive(archiveName)
    archive.load()

    # An non-existant or empty list would extract everything - don't allow
    if not extractList:
        return

    try:
        # Filter the list
        result = archive.find(extractList)
    except pak.ArchiveError as e:
        out.print(str(e))
        return

    # Write the files
    for entry in result:
        savedArch.append(entry)
        archive.remove(entry)

    # Write it back out
    archive.save()

    return

def restoreSaved(archiveName, savedArc):
    archive = pak.Archive(archiveName)
    archive.load()

    for entry in savedArc:
        archive.append(entry)

    archive.save()

def stub_cp(src, dir):
    os.makedirs(dir,exist_ok=True)
    for f in src:
        cmd = "cp %s %s/" % (f,dir)
        resp = subprocess.run(cmd.split())

############################################################
# Main - Main - Main - Main - Main - Main - Main - Main
############################################################

imageToolDir = os.path.dirname(sys.argv[0])
parser = argparse.ArgumentParser(description="Build image",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=textwrap.dedent('''

examples:
  > imageBuild.py configs/odyssey/dd1/ody_pnor_dd1_image_config -o ./image_output -n pnor.bin
'''))

parser.add_argument('configfile', help="The configuration file used to build the image.")
parser.add_argument('-b','--build',action='store_true',
                    help='Download repos (if not found), checkout commit and build it')
parser.add_argument('--nobranchchange', action='store_true', help="Don't change the branch when building")
parser.add_argument('--update', action='store_true', help="After changing to specified branch, update it from the server as well")
parser.add_argument('--devready', action='store_true', help="Apply dev-ready ekb commits on top of branch")
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
sbeImageDir = os.path.join(sbeBase,'images')

imageToolDir = os.path.realpath(os.path.expanduser(imageToolDir))
pakBuildTool    = os.path.join(imageToolDir, 'pakbuild.py')
pakTool         = os.path.join(imageToolDir, 'paktool')
flashBuildTool  = os.path.join(imageToolDir, 'flashbuild.py')

#signTool = os.path.join(imageToolDir,'signHashList')
# TODO these will be in sbe, not imageToolDir
signTool = os.path.join(imageToolDir,'signimage')
hashTool = os.path.join(imageToolDir,'imagehash')

output    = os.path.abspath(args.output)
imagefile = os.path.join(output,args.name)
genDir = os.path.join(output,'gen')
os.makedirs(genDir,exist_ok=True)

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
        '%sbeImageDir%' : sbeImageDir,
        '%sbeRoot%'     : sbeBase,
        '%gen%'         : genDir,
}

#### build stages
stage1 = 'merged'
stage2 = 'signed'
stage3 = 'final'

mergedDir = os.path.join(genDir,stage1)
signedDir = os.path.join(genDir,stage2)
finalDir  = os.path.join(genDir,stage3)

os.makedirs(mergedDir,exist_ok=True)
os.makedirs(signedDir,exist_ok=True)
os.makedirs(finalDir,exist_ok=True)

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
signImgSrc = []
hashImgSrc = []
notHashed = {}

for sectionName, info in section_info.items():
    if not info['mergedArchive']:
        continue

    pakname = info['mergedArchive']

    ## Extract and save entries that should not be hashed, then remove them from the archive
    saveArchive = pak.Archive()
    if 'noHash' in info.keys():
        saveAndRemove(pakname, saveArchive, info['noHash'])

    if 'hashlist' in info.keys():
        #----------------------------
        # Generate hash.list
        #----------------------------
        hashpath = info['hashpath']
        hashlist = info['hashlist']

        # hashname in archive
        archivefn = os.path.join(hashpath,hashlist)

        # full path filesystem
        outhash = os.path.join(output, hashpath)
        os.makedirs(outhash,exist_ok=True)

        # create hash list and add it to the archive
        makeHashList(pakname, archivefn)

        # Must be signed, so source pak to sign comes from stage1
        signImgSrc.append(pakname)
        # Must be hashed, so source pakname to hash comes from stage2
        hashImgSrc.append(pakname.replace(stage1,stage2))
    else:
        # Not to be signed, only hashed, so source pakname to hash is from stage1.
        hashImgSrc.append(pakname)

    # All paks will exist in stage3 - used to build final flash image
    finalName = pakname.replace(stage1,stage3)
    section_info[sectionName]['finalArchive'] = finalName
    notHashed[sectionName] = saveArchive

#----------------------------
# Call signTool
#----------------------------
cmd = "%s -i %s -o %s" % (
        signTool,
        ' '.join(signImgSrc),
        signedDir)

if os.path.exists(signTool):
    resp = subprocess.run(cmd.split)
    if resp.returncode != 0:
        print("%s failed with rc %d" % (cmd,resp.returncode))
        sys.exit(resp.returcode)
else:
    print(cmd)
    stub_cp(signImgSrc, signedDir)


#--------------------------------
# Call hashTool
#--------------------------------
cmd = "%s -i %s -o %s" % (
        hashTool,
        ' '.join(hashImgSrc),
        finalDir)

if os.path.exists(hashTool):
    resp = subprocess.run(cmd.split)
    if resp.returncode != 0:
        print("%s failed with rc %d" % (cmd,resp.returncode))
        sys.exit(resp.returncode)
else:
    print(cmd)
    stub_cp(hashImgSrc, finalDir)


# Create image
cmd = "%s build-image %s %s" % (flashBuildTool, partitionsfile, imagefile)
#----------------------------
# Restore images not hashed
#----------------------------
for sectionName, info  in section_info.items():
    archive = notHashed[sectionName]
    restoreSaved(info['finalArchive'], archive)
    cmd = "%s -p %s=%s" % (cmd, sectionName, info['finalArchive'])
#print(cmd)
#-------------------------
# Create final image
#-------------------------
resp = subprocess.run(cmd.split())
if resp.returncode != 0:
    print("flashbuild failed with rc %d" % resp.returncode)
    sys.exit(resp.returncode)







