#!/usr/bin/env python3
import sys
import os
import argparse
import textwrap
import subprocess
import ast
import shutil
import tarfile
import inspect

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

    return mergedArchiveFile

def setupRepository(basePath, commit,remote):
    print("basePath: %s" % basePath)
    if not os.path.exists(basePath):
        if not args.no_downloads:
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
        cmd= config['sbeWorkon']
        build_cmd=config['sbeBuild']
        if (args.devready or args.devreadysbe):
            if not args.nobranchchange:
                getDevReadyCommits('sbe', commit)
            else:
                print("Not getting dev-ready updates because --nobranchchange was specified")

    elif 'ekb' in remote:
        cmd= config['ekbWorkon']
        build_cmd= config['ekbBuild']
        if (args.devready or args.devreadyekb):
            if not args.nobranchchange:
                getDevReadyCommits('ekb', commit)
            else:
                print("Not getting dev-ready updates because --nobranchchange was specified")
    else:
        print('Unknown remote: %s' % remote,file=sys.stderr)
        os.chdir(cwd)
        sys.exit(1)

    with subprocess.Popen(cmd.split(),stdin=subprocess.PIPE) as proc:
        proc.communicate(input=str.encode(build_cmd))
        if proc.returncode != 0:
            print("Building %s had a returncode %d" % (
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

def getDevReadyCommits(repo, commit):
    print("\nRunning ./", repo, " cronus checkout")
    if (repo == 'sbe'):
        dev_out_file = 'cro_ody_sbe_image_cronus_checkout.sversion'
        dev_out, err = subprocess.Popen(['export PROJECT_NAME=sbe; export SBEROOT=`pwd` export SBEROOT_INT=`pwd`/internal; export SBE_INSIDE_WORKON=1; source ./internal/projectrc; ./sbe cronus_devready checkout; unset SBE_INSIDE_WORKON; unset PROJECT_NAME; unset SBEROOT; unset SBEROOT_INT;'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True).communicate()
    else:
        dev_out_file = 'cro_ody_ekb_image_cronus_checkout.sversion'
        dev_out, err = subprocess.Popen(['source ./env.bash; ./ekb cronus checkout --branch', commit], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True).communicate()
    # Sometimes seeing stuff in stderr that isn't actually an error, so not going to fail
    if err:
        print("INFO: stderr returned:\n", err)

    print(repo, " cronus checkout --branch", commit, "\n")
    print(dev_out)

    # look for explicit problems
    if ('Outstanding tracked changes' or 'Not a git repository' or 'Run this tool from the root' or 'Cherry-picks failed') in dev_out:
        print("ERROR! Failed checking of dev-ready checkouts\n", dev_out)
        os.chdir(cwd)
        sys.exit(1)

    # look for confirmation it worked
    if not ('Checking out' and 'All Cherry-picks applied cleanly') in dev_out:
        print("ERROR! Failed checking out dev-ready checkouts\n", dev_out)
        os.chdir(cwd)
        sys.exit(1)

    # write output to a file
    filename = os.path.join(output, dev_out_file)
    outfile = open(filename, 'w')
    outfile.write(dev_out)
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
    for f in src.values():
        cmd = "cp %s %s/" % (f,dir)
        resp = subprocess.run(cmd.split())

def download(url, dir):
    os.makedirs(dir,exist_ok=True)
    cmd = f"wget {url} -P {dir}"
    print(cmd)
    resp = subprocess.run(cmd.split())
    if resp.returncode != 0:
        print(f"{cmd} failed with rc {resp.returncode}")
        sys.exit(resp.returncode)
    return os.path.join(dir,os.path.basename(url))

def downloadBinaries(output):
    cwd = os.getcwd()
    binariesDir=os.path.join(output,"binaries")
    if os.path.exists(binariesDir):
        shutil.rmtree(binariesDir)
    os.makedirs(binariesDir)
    downloads = os.path.join(output,"downloads")
    if os.path.exists(downloads):
        shutil.rmtree(downloads)
    os.makedirs(downloads)
    if 'binaries' in config.keys():
        repoName = "released"
        repoPath = os.path.join(downloads,repoName)
        os.chdir(downloads)
        cmds=config['binaries']['repository']
        for cmd in cmds:
            if cmd.startswith('git clone'):
                cmd = f"{cmd} {repoName}"
            print(cmd)
            resp=subprocess.run(cmd.split())
            if resp.returncode != 0:
                os.chdir(cwd)
                print(f"ERROR: {cmd} failed with rc {resp.returncode}")
                sys.exit(resp.returncode)

        os.chdir(repoName)
        # get base commit id
        cmd = f"git log --oneline -n 1"
        resp=subprocess.run(cmd.split(),stdout=subprocess.PIPE)
        baseCommit = resp.stdout.decode().split()[0]
        if resp.returncode != 0:
            os.chdir(cwd)
            print(f"ERROR: {cmd} failed with rc {resp.returncode}")
            sys.exit(resp.returncode)

        files = config['binaries']['files']
        for file,commit in files:
            if commit == '':
                commit = baseCommit
            cmd = f"git checkout {commit}"
            print(f"INFO: {cmd}")
            resp=subprocess.run(cmd.split(),stderr=subprocess.PIPE)
            if resp.returncode != 0:
                print(f"ERROR: {cmd} failed with rc {resp.returncode}")
                os.chdir(cwd)
                sys.exit(resp.returncode)

            srcpath=os.path.join(repoPath,file)
            dstpath=os.path.join(binariesDir,os.path.basename(file))
            cmd = f"cp {srcpath} {dstpath}"
            resp=subprocess.run(cmd.split())
            if resp.returncode != 0:
                print(f"ERROR: {cmd} failed with rc {resp.returncode}")
                os.chdir(cwd)
                sys.exit(resp.returncode)
        os.chdir(cwd)
    else:
        os.makedirs(binariesDir,exist_ok=True)

    if os.path.exists(downloads):
        shutil.rmtree(downloads)

    # create binaries map
    binaries = {}
    files = os.listdir(binariesDir)
    for f in files:
        fullpath= os.path.join(binariesDir,f)
        if os.path.isfile(fullpath):
            binaries[f] = fullpath
    return (binariesDir,binaries)

def resolveFile(fpath, replacement_tags, overrides, binaries):
    # replace tags
    for key,value in replacement_tags.items():
        fpath = fpath.replace(key,value)
    # First look for the file in the overrides
    # If not there then check fpath
    # If not there then look in binaries
    fname =  os.path.basename(fpath)
    if fname in overrides.keys():
        newPath = overrides[fname]
    elif os.path.exists(fpath):
        newPath = fpath
    elif fname in binaries.keys():
        newPath = binaries[fname]
    else:
        print(f"ERROR Required file not found: {fname}")
        sys.exit(1)

    tgzext = '.tar.gz'
    if newPath.endswith(tgzext):
        # untar tar -C binaries -xzf binaries/sbe_images/odyssey_dd1_0/golden/golden_odyssey_nor_DD1.img.tar.gz
        tar = tarfile.open(newPath)
        # TODO might want to consider case where newPath is in an unwriteable location
        if 'filter' in inspect.signature(tarfile.TarFile.extractall).parameters:
            tar.extractall(os.path.dirname(newPath),filter="data")
        else:
            tar.extractall(os.path.dirname(newPath))
        newPath=newPath[:-len(tgzext)]
    print(f"INFO: Using {newPath}")
    return newPath


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

parser.add_argument('configfile',
                    help="The configuration file used to build the image.")
parser.add_argument('-b','--build',action='store_true',
                    help='Downloads ekb and sbe repositories (if not found), '
                    'then checks out branchs and builds them. Note: Requires '
                    ' --ekb and --sbe, or --build_workdir')
parser.add_argument('--nobranchchange', action='store_true',
                    help="Don't change the branch when building")
parser.add_argument('--update', action='store_true',
                    help='After changing to specified branch, '
                    'update it from the server as well')
parser.add_argument('--devready', action='store_true',
                    help='Apply dev-ready ekb and sbe commits on top of branch')
parser.add_argument('--devreadyekb', action='store_true',
                    help='Apply dev-ready ekb commits on top of branch')
parser.add_argument('--devreadysbe', action='store_true',
                    help='Apply dev-ready sbe commits on top of branch')
parser.add_argument('--ekb',default=None,
                    help='Base path of the ekb git repository.'
                    ' Use --ekb_images instead for pre-built images')
parser.add_argument('--ekb_images',default=None,
                    help='Image directory of pre-built ekb images.')
parser.add_argument('--sbe',default=None,
                    help='Base path of sbe repository or sbe images. Default: use value '
                    'in configfile')
parser.add_argument('--ovrd',default=None,
                    help='Directory to look for override source files.'
                    ' Files must have same name as those being overridden')
parser.add_argument('-o','--output', default='./image_output',
                    help='output directory. default ./image_output')
parser.add_argument('-n','--name', default='image.bin',
                    help='output image filename. default: image.bin')
parser.add_argument('--pakToolDir',default=None,
                    help='Directory of PAK tools. '
                    'PAK tool override. Only required if PAK tools not available in '
                    'ekb,sbe,or sbe_tools.')
parser.add_argument('--sbe_test',action='store_true',
                    help='Run sbe test cases to validate the images')
parser.add_argument('--build_workdir', type=str,
                    help='Work directory for the build. '
                    'Tool will ignore xxxxRoot configure parameter value.')
parser.add_argument('--buildGoldenImg', type=int, metavar="SIDE_COUNT",
                    help='Use to build golden image with the side count '
                         'instead of the configured frozen golden image.'
                         'The golden image will be used for the given sides.')
parser.add_argument('--allowToSign', action='store_true',
                    help='Use to allow the signing process for the frozen '
                         'configured image_sections.')
parser.add_argument('--no_downloads', action='store_true',
                    help='Disable downloading any repositories/binaries etc.')
parser.add_argument('--disable_arch_nor_img', action='store_true',
                    help='disable nor image copy into debug archive')
args = parser.parse_args()

# process the configuration file and load needed modules whos location is based on
# the configuration
configFile = os.path.abspath(args.configfile)
if(not os.path.exists(configFile)):
    print("The given config file: '%s', does not exist!" % configFile, file=sys.stderr)
    sys.exit(1)

cwd = os.getcwd()

configdir = os.path.dirname(configFile)

config = readConfigFile(configFile)

# Get the architecture that's running.
resp = subprocess.run(["uname","-m"],stdout=subprocess.PIPE)
exe_arch = resp.stdout.decode('utf-8').rstrip()

# Get the target architecture if available
target_arch = os.environ.get("ECMD_ARCH")
if not target_arch:
    target_arch = exe_arch

output    = os.path.abspath(args.output)
os.makedirs(output,exist_ok=True)

if args.ekb and args.ekb_images:
    print("ERROR Can't use --ekb and --ekb_images together.")
    sys.exit(1)

if not args.ekb and not args.ekb_images and not args.ovrd and not args.build_workdir:
    print("ERROR Needs to specify either --ekb or --ekb_images or --ovrd or --build_workdir")
    sys.exit(1)

if args.build and not args.ekb and not args.build_workdir:
    print("ERROR --build requires --ekb or --build_workdir")
    sys.exit(1)

## ekb base
ekbBase = args.ekb
ekbImageDir = ''

if ekbBase:
    ekbBase = os.path.realpath(os.path.expanduser(ekbBase))
    ekbImageDir = config['ekbImageSubDir'].replace('%machine_arch%',target_arch)
    ekbImageDir = os.path.join(ekbBase,ekbImageDir)
else:
    if args.ekb_images:
        ekbBase = args.ekb_images
    elif args.build_workdir:
        ekbBase = os.path.abspath(os.path.join(args.build_workdir, 'ekb'))
    else:
        ekbBase = args.ovrd

    ekbBase = os.path.realpath(os.path.expanduser(ekbBase))
    ekbImagDir = ekbBase

## sbe base
sbeBase = args.sbe
if not sbeBase:
    if args.build_workdir:
        sbeBase = os.path.abspath(os.path.join(args.build_workdir, 'sbe'))
    elif 'sbeRoot' in config.keys():
        sbeBase = config['sbeRoot']
    else:
        print("Critical! No path to sbe repository")
        sys.exit(1)

sbeBase = os.path.realpath(os.path.expanduser(sbeBase))
sbeImageDir = os.path.join(sbeBase,'images')

# setup git repos and build - only if --build option specified.
if args.build:
    setupRepository(ekbBase, config['ekbCommit'],'hw/ekb-src')
    setupRepository(sbeBase, config['sbeCommit'],'hw/sbe')
os.chdir(cwd)

## Load overrides
overrides = {}
if args.ovrd:
    path = os.path.realpath(os.path.expanduser(args.ovrd))
    if os.path.exists(path):
        files = os.listdir(path)
        for f in files:
            fullpath = os.path.join(path,f)
            if os.path.isfile(fullpath):
                overrides[f] = fullpath
    else:
        print("WARN override directory does not exist: %s" % path)

## Load released binaries
binariesDir = ''
binaries = {}
if not args.no_downloads:
    binariesDir,binaries = downloadBinaries(output)

# Untar sbe_tools.tar.gz to get sbe tools
sbeToolsTar = config['sbeTools']
if(sbeToolsTar in overrides.keys()):
    sbeToolsTar = overrides[sbeToolsTar]
else:
    sbeToolsTar = os.path.join(sbeImageDir, sbeToolsTar)

sbeTools = tarfile.open(sbeToolsTar)

if 'filter' in inspect.signature(tarfile.TarFile.extractall).parameters:
    sbeTools.extractall(output,filter="data")
else:
    sbeTools.extractall(output)

sbeToolsDir = os.path.join(output,'sbe_tools')
sbeImageTool = os.path.join(sbeToolsDir, 'imageTool.py')

sbeEccTool = os.path.join(sbeToolsDir,'ecc')
if not os.path.exists(sbeEccTool):
    print("ERROR: %s does not exist. Make sure SBE is current" % sbeEccTool)
    sys.exit(1)


## pak tools
pakToolsDir = args.pakToolDir
if(pakToolsDir):
    pakToolsDir = os.path.realpath(os.path.expanduser(pakToolsDir))
else:
    # First, look in sbe tools
    # TODO where under sbeToolsDir will pak tools be?
    pakToolsDir = os.path.join(sbeToolsDir,'tools')
if not os.path.exists(os.path.join(pakToolsDir,'paktool')):
    # Next, look in sbe path
    pakToolsDir = os.path.join(sbeBase,'public','src','import','public',
                               'common','utils','imageProcs','tools')
if not os.path.exists(pakToolsDir):
    # Finally, look in ekb path
    pakToolsDir = os.path.join(ekbBase,'public','common','utils',
                               'imageProcs','tools')
    if not os.path.exists(pakToolsDir):
        print("ERROR:  Can't find paktools")
        sys.exit(1)

imageToolDir = os.path.realpath(os.path.expanduser(imageToolDir))
pakTool         = os.path.join(pakToolsDir, 'paktool')
flashBuildTool  = os.path.join(pakToolsDir, 'flashbuild')


imagefile = os.path.join(output,args.name)
singleImagefile = imagefile
concatCopies = 0
if 'concat' in config.keys():
    concatCopies = config['concat']
if concatCopies > 1:
    singleImagefile = os.path.join(output,"single_" + args.name)

if os.path.exists(imagefile):
    os.remove(imagefile)
if os.path.exists(singleImagefile):
    os.remove(singleImagefile)

genDir = os.path.join(output,'gen')
if os.path.exists(genDir):
    shutil.rmtree(genDir)
os.makedirs(genDir)

# Required before calling pak tools
sys.path.append("%s/pymod" % pakToolsDir)

from output import out
import pakcore as pak

#only print out critical errors. For debug, change CRITICAL to DEBUG
out.setConsoleLevel(out.levels.CRITICAL)

section_info = config['image_sections']

#### Build stages
####    Note : Below stage will be skipped if section is configured with 'signed_image'
####           and '--allowToSign' option is not passed since the SBE provides
####           frozen signed images so tool should not attempt to sign.
stage1 = 'merged'
stage2 = 'signed'
stage3 = 'final'  #hashed

mergedDir = os.path.join(genDir,stage1)
signedDir = os.path.join(genDir,stage2)
finalDir  = os.path.join(genDir,stage3)

os.makedirs(mergedDir,exist_ok=True)
os.makedirs(signedDir,exist_ok=True)
os.makedirs(finalDir,exist_ok=True)

#
replacement_tags = {
        '%binariesDir%'  : binariesDir,
        '%imageToolDir%' : imageToolDir,
        '%ekbImageDir%' : ekbImageDir,
        '%sbeImageDir%' : sbeImageDir,
        '%sbeRoot%'     : sbeBase,
        '%gen%'         : genDir,
}

# Discover partitions
partitions = []
for sectionName, info in section_info.items():
    partitions.append((sectionName, info['partition_size']))

# Create partitions file and build partition table
partitionsfile = buildPartitionTable(partitions)

# Resolve archive paths in image_sections
# Merge archives where more than one exists in an image section
for sectionName, info in section_info.items():
    if 'signed_image' in info.keys() and not args.allowToSign:
        print(f"INFO: Use configured signed image for '{sectionName}' so no signing...")
        continue

    archives    = []
    baseEntries = []

    # Resolve location of archive images
    for arc in info['archives']:

        arc = resolveFile(arc, replacement_tags, overrides, binaries)
        archives.append(arc)

    if 'files' in info.keys():
        for (entryName,entryPath) in info['files']:
            for key,value in replacement_tags.items():
                entryPath = entryPath.replace(key,value)
            baseEntries.append((entryName,entryPath))

    # merge archives
    section_info[sectionName]['mergedArchive'] = mergeArchives(sectionName, archives, baseEntries)


# Add signature/hash to sections that require it
signImgSrc = {}
hashImgSrc = {}
asisImgSrc = {}

notHashed = {}

for sectionName, info in section_info.items():
    if 'mergedArchive' not in info.keys():
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

        # create hash list and add it to the archive
        makeHashList(pakname, archivefn)

        # Must be signed, so source pak to sign comes from stage1
        signImgSrc[sectionName] = pakname
        # Must be hashed, so source pakname to hash comes from stage2
        hashImgSrc[sectionName] = pakname.replace(stage1,stage2)
    elif 'imagehash' in info.keys():
        # Not to be signed, only hashed, so source pakname to hash is from stage1.
        hashImgSrc[sectionName] = pakname

    else:
        asisImgSrc[sectionName] = pakname

    # All paks will exist in stage3 - used to build final flash image
    finalName = pakname.replace(stage1,stage3)
    section_info[sectionName]['finalArchive'] = finalName
    notHashed[sectionName] = saveArchive

#----------------------------
# Call sbeImageTool signPak
#----------------------------
# If running in op-build use the host dir
if os.environ.get('HOST_DIR'):
    os.environ['OPBUILD_HOST_DIR'] = os.environ.get('HOST_DIR')
    os.environ['OPEN_SSL_PATH']='/bin/openssl'
else:
    # This is ugly ... need support for more than RHEL and don't point to someones user space
    with subprocess.Popen("lsb_release -sr".split(),stdout=subprocess.PIPE) as proc:
        osversion = proc.stdout.read().decode()
    if osversion[0] == '8':
        os.environ['SIGNING_RHEL_PATH']='/gsa/rchgsa/home/c/e/cengel/signtool/RHEL8/'
        os.environ['OPEN_SSL_PATH']='/bin/openssl'
    elif osversion[0] == '7':
        os.environ['SIGNING_RHEL_PATH']='/gsa/rchgsa/home/c/e/cengel/signtool/RHEL7/'
        os.environ['OPEN_SSL_PATH']='/gsa/rchgsa/home/c/e/cengel/signtool/RHEL7/openssl-1.1.1n/apps/openssl'
    else:
        print("ERROR: Signing is only available for os RHEL7 and RHEL8");
        sys.exit(1)

pakFilesToSign = ""
for sectionName, pakFile in signImgSrc.items():
    pakFilesToSign += sectionName + "=" + pakFile + " "

cmd = f"{sbeImageTool} --pakToolDir {pakToolsDir} \
        signPak --pakFiles {pakFilesToSign}"

print(f"INFO: signing: {pakFilesToSign}")

if os.path.exists(sbeImageTool):
    resp = subprocess.run(cmd.split())
    if resp.returncode != 0:
        print("%s failed with rc %d" % (cmd,resp.returncode))
        sys.exit(resp.returncode)
    else:
        stub_cp(signImgSrc, signedDir)

#--------------------------------
# Call sbeImageTool pakHash
#--------------------------------
pakFilesToHash = ""
for sectionName, pakFile in hashImgSrc.items():
    pakFilesToHash += sectionName + "=" + pakFile + " "

cmd = f"{sbeImageTool} --pakToolDir {pakToolsDir} \
        pakHash --pakFiles {pakFilesToHash}"

print(f"INFO: hashing: {pakFilesToHash}")

if os.path.exists(sbeImageTool):
    resp = subprocess.run(cmd.split())
    if resp.returncode != 0:
        print("%s failed with rc %d" % (cmd,resp.returncode))
        sys.exit(resp.returncode)
    else:
        stub_cp(hashImgSrc, finalDir)

stub_cp(asisImgSrc, finalDir)

# Use configured 'signed_image' as 'finalArchive' to pack since signing were
# skipped for those image sections
for sectionName, info  in section_info.items():
    if 'signed_image' in info.keys() and not args.allowToSign:
        print(f"INFO: Copy the configured signed image for '{sectionName}' as final image...")
        signedImgPath = info['signed_image']
        for key,value in replacement_tags.items():
            signedImgPath = signedImgPath.replace(key,value)

        finalArchivePath  = os.path.join(finalDir, f"{sectionName}.pak")
        shutil.copy(signedImgPath, finalArchivePath)
        section_info[sectionName]['finalArchive'] = finalArchivePath

# Create image
cmd = "%s build-image %s %s" % (flashBuildTool, partitionsfile, singleImagefile)

#----------------------------
# Restore images not hashed
#----------------------------
for sectionName, info  in section_info.items():
    if sectionName in notHashed.keys():
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

if concatCopies > 1:
    shutil.copyfile(singleImagefile, imagefile)

    if args.buildGoldenImg:
        print(f"INFO: Using the custom golden image for the given "
              f"side count [{args.buildGoldenImg}]")
        concatCopies = args.buildGoldenImg

    f1 = open(imagefile, 'ab+')
    for i in range(concatCopies-1):
        f = open(singleImagefile, 'rb')
        f1.write(f.read())
        f.close()

    if 'golden_image' in config.keys() and not args.buildGoldenImg:
        print("INFO: Using configured golden image to pack in the NOR image")
        goldenImgPath = config['golden_image']

        goldenImgPath = resolveFile(goldenImgPath, replacement_tags, overrides, binaries)

        goldenImgFd = open(goldenImgPath, 'rb')
        f1.write(goldenImgFd.read())
        goldenImgFd.close()

    f1.close()

    if not args.disable_arch_nor_img and "lab_image_config" not in args.configfile:
        print("INFO: Odyssey pnor image config")
        # Copy odyssey_nor_DD1.img into odyssey_sbe_debug_DD1.tar.gz
        archSbeDebugTar = os.path.join(sbeImageDir, "odyssey/odyssey_sbe_debug_DD1.tar.gz")
        if not os.path.exists(archSbeDebugTar):
            print(f"{archSbeDebugTar} does not exist", file=sys.stderr)
            sys.exit(1)
        else:
            print("INFO: Untar odyssey_sbe_debug_DD1.tar.gz")
            archive = tarfile.open(archSbeDebugTar)
            pathSbeDebugTar = os.path.dirname(os.path.abspath(archSbeDebugTar))

            if 'filter' in inspect.signature(tarfile.TarFile.extractall).parameters:
                archive.extractall(pathSbeDebugTar,filter="data")
            else:
                archive.extractall(pathSbeDebugTar)

            archive.close()

            # Remove odyssey_sbe_debug_DD1.tar.gz
            os.remove(archSbeDebugTar)

            print("INFO: Copy odyssey_nor_DD1.img into extracted odyssey_debug_files_tools")
            pathSbeDebugTools = os.path.join(pathSbeDebugTar, "odyssey_debug_files_tools")
            shutil.copy(imagefile, pathSbeDebugTools)

            print("INFO: Archive odyssey_debug_files_tools into tar file odyssey_sbe_debug_DD1.tar.gz")
            archive = tarfile.open(archSbeDebugTar, "w:gz")
            archive.add(pathSbeDebugTools, arcname=os.path.basename(pathSbeDebugTools))
            archive.close()

            # Remove directory odyssey_debug_files_tools
            shutil.rmtree(pathSbeDebugTools)

#--------------------------
# ecc
#--------------------------
eccImagefile = imagefile+'.ecc'
cmd = "%s --inject %s --output %s --p8" % (sbeEccTool,imagefile,eccImagefile)
resp = subprocess.run(cmd.split())
if resp.returncode != 0:
    print("ecc failed with rc %d" % resp.returncode)
    sys.exit(resp.returncode)

#--------------------------
# Run SBE test cases
#--------------------------
if args.sbe_test:
    print("------------------------")
    print("Running SBE test cases")
    print("------------------------")
    if not os.path.exists(sbeBase):
        print(f"{sbeBase} is not exist", file=sys.stderr)
        sys.exit(1)
    elif not os.path.exists(os.path.join(sbeBase, "internal")):
        print(f"Not found 'internal' directory in {sbeBase} to run test cases")
        sys.exit(1)

    os.chdir(sbeBase)

    workon_cmd = config['sbeWorkon']
    runtest_cmd = f"./sbe runtest {output}"
    with subprocess.Popen(workon_cmd.split(),stdin=subprocess.PIPE) as proc:
        proc.communicate(input=str.encode(runtest_cmd))
        if proc.returncode != 0:
            print(f"SBE test cases is failed, returncode: {proc.returncode}",
                  file=sys.stderr)
            os.chdir(cwd)
            sys.exit(1)

    os.chdir(cwd)
