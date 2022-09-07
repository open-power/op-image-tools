#!/usr/bin/env python3
# IBM_PROLOG_BEGIN_TAG
# This is an automatically generated prolog.
#
# $Source: public/common/utils/imageProcs/tools/flashbuild $
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

from argparse import ArgumentParser, ArgumentTypeError
from ast import literal_eval
import sys, os

# Add program modules to the path
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "pymod"))
from pakcore import Archive, PAK_END

PART_NAME_MAXLEN = 16
PT_FORMAT_VER = 1

class Partition(object):
    def __init__(self, name, start, size, last):
        if len(name) > PART_NAME_MAXLEN:
            raise ValueError("Partition name '%s' exceeds maximum length of %d bytes" % (name, PART_NAME_MAXLEN))
        self.name = name
        self.start = start
        # Space for the end marker on the last entry
        self.size = size - (8 if last else 0)
        self.last = last
        self.pak = Archive()
        self.pak.end_marker = False

    def load_pak(self, fname):
        self.pak.filename = fname
        self.pak.load()

        # Make sure the pak isn't bigger than the partition
        if len(self.pak.image) > self.size:
            raise ValueError("Partition '%s': Partition image '%s' exceeds available space (%d > %d)" %
                             (self.name, fname, len(self.pak.image), self.size))

        # If the end marker is there, strip it off the pak
        # Also disable it being re-added when the pak image is rebuilt
        if self.pak.end_marker:
            self.pak.image = self.pak.image[:-8]
        self.pak.end_marker = False

    def expand(self):
        # Calc the size to pad
        size = self.size - len(self.pak.image)
        self.pak.addPad(size)

    def write_partition(self, f):
        # Rebuild the pak image before the write
        self.pak.build()
        f.write(self.pak.image)

    def table_entry(self):
        name = self.name.encode()
        return name + bytes(-len(name) % PART_NAME_MAXLEN) + self.start.to_bytes(4, 'big') + self.size.to_bytes(4, 'big')

def cmd_build_image(args, partitions):
    partition_index = {p.name: p for p in partitions}
    for pname, fname in args.partition:
        try:
            partition_index[pname].load_pak(fname)
        except KeyError:
            print("Unknown partition name: " + pname)
            exit(1)

    with open(args.outfile, "wb") as image:
        for part in partitions:
            part.expand()
            part.write_partition(image)

        # Add a new end marker with the updated total size
        image.write(PAK_END.to_bytes(4, 'big'))
        image.write((image.tell() + 4).to_bytes(4, 'big'))

def cmd_concat_image(args, partitions):
    '''
    concatenate archives. No checking for duplicate files
    '''
    outpName = os.path.basename(args.outfile)
    outpName = outpName.replace('.pak','')
    maxsize = 0

    for p in partitions:
        if outpName == p.name:
            maxsize = p.size
            break
    if maxsize == 0:
        print("Unknown partition name: " + outpName)
        exit(1)

    # Make sure all source images can be loaded
    npartitions = []
    asize = maxsize
    offset = 0
    for pname, fname in args.partition:
        part = Partition(pname, offset, asize, False)
        part.load_pak(fname)
        asize = asize - len(part.pak.image)
        offset = offset + len(part.pak.image)
        npartitions.append(part)

    with open(args.outfile, "wb") as image:
        for part in npartitions:
            print("write %s" % part.name)
            part.write_partition(image)
        # Add end marker with
        image.write(PAK_END.to_bytes(4, 'big'))
        image.write((image.tell() + 4).to_bytes(4, 'big'))


def cmd_compile_ptable(args, partitions):
    with open(args.outfile, "wb") as f:
        f.write(b"PTBL")
        f.write(PT_FORMAT_VER.to_bytes(2, 'big'))
        f.write(len(partitions).to_bytes(2, 'big'))
        for p in partitions:
            f.write(p.table_entry())

def pspec(arg):
    parts = arg.split("=")
    if len(parts) != 2:
        raise ArgumentTypeError("Partition specification must be part_name=file_name")
    return parts

if __name__ == "__main__":
    parser = ArgumentParser(description="Utilities around pak based flash images")
    subparsers = parser.add_subparsers()

    sub = subparsers.add_parser("build-image", help="Build a flash image from individual pak partitions")
    sub.add_argument("parttable", type=open, help="Partition table description")
    sub.add_argument("outfile", help="Output image file name")
    sub.add_argument("--partition", "-p", action="append", default=[], type=pspec, help="Partition images in part_name=file_name format")
    sub.set_defaults(func=cmd_build_image)

    sub = subparsers.add_parser("compile-ptable", help="Translate a text partition table into binary")
    sub.add_argument("parttable", type=open, help="Partition table description")
    sub.add_argument("outfile", help="Output file name")
    sub.set_defaults(func=cmd_compile_ptable)

    sub = subparsers.add_parser("concat-image",help="concatinate pak images into one")
    sub.add_argument("parttable", type=open, help="Partition table description")
    sub.add_argument("outfile", help="Output image file name")
    sub.add_argument("--partition", "-p", action="append", default=[], type=pspec, help="Partition images in part_name=file_name format")
    sub.set_defaults(func=cmd_concat_image)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        exit(1)

    partition_table = literal_eval(args.parttable.read())
    partitions = []
    offset = 0
    for i, (name, size) in enumerate(partition_table):
        last = i == (len(partition_table) - 1)
        partitions.append(Partition(name, offset, size, last))
        offset += size

    args.func(args, partitions)
