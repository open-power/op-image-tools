#!/usr/bin/env python3
# IBM_PROLOG_BEGIN_TAG
# This is an automatically generated prolog.
#
# $Source: public/common/utils/imageProcs/tools/pymod/pakcore.py $
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

############################################################
# Imports - Imports - Imports - Imports - Imports - Imports
############################################################
import zlib
import os
import sys
import struct
from collections import UserList
from enum import IntEnum
from output import out
import ast
import fnmatch
import copy
import hashlib

############################################################
# Classes - Classes - Classes - Classes - Classes - Classes
############################################################
class CM(IntEnum):
    '''
    Define the compression methods

    Note: I too believe defines should be in CAPS
    However, by defining them lowercase the convenience parts all just works much smoother
    i.e.. it matches the input in the manifest and on the cmdline
    '''
    store = 1
    zlib = 2
    zlib_fast = 3
    zlib_ppc = 4

    # Needed to make choices in argparse work
    def argparse(self):
        try:
            return CM[self]
        except KeyError:
            return self

    # Removes the CM. off prints in argparse
    def __str__(self):
        return self.name

    # Prints an easy to read list of options
    def __repr__(self):
        return str(self)

class ArchiveError(Exception):
    '''
    Put most program errors through exceptions instead of return codes
    Give us hooks into the messages should it be needed
    '''
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return self.message

##############################
# All archive related info
##############################
# Magic to indicate a file entry
PAK_FILE = 0x50414B21 # PAK!
# Magic to indicate a pad entry
# The 4 byte size of the pad follows, making it an 8 byte block
PAK_PAD = 0x50414B50 # PAKP
# Magic to indicate pak end
# The 4 byte total length of the archive follows,  making it an 8 byte block
PAK_END = 0x2F50414B # /PAK
# Track version changes in the pak format
PAK_VERSION = 1

# If a file is added with a fixed size, store that in the header flags
# This would preserve the psize should the archive be rewritten
PAK_FLAG_FIXED_SIZE = 0x20

class ArchiveEntry(object):
    def __init__(self, i_type=PAK_FILE):
        '''
        Define the structure of a .pak file entry
        The contents is created by unpacking data into it or through ingest
        '''
        ################
        # Start Format #
        ################

        #################
        # Header Core
        # A single 8 byte block that describes core info about the entry
        #
        # 4 bytes - a sanity check we are at the start
        # This can now be for either a file or pad
        # We do not store the end marker as an archive entry
        self.magic = i_type

        # The next 4 bytes depends on the magic type
        # PAK_PAD
        # The pad case is very simple - it just 1 8 byte total block
        # 4 bytes - the size of the pad to follow
        self.padsize = None

        # PAK_FILE
        # The pak file entry is more complex, finish out the header core definition
        # 2 byte - the version
        self.version = PAK_VERSION
        # 2 bytes - the size header extended, to guide the next read
        #self.hesize - a derived property function

        #################
        # Header Extended
        # The extended 8 byte aligned header containing aditional info and the name
        #
        # 1 byte - defined bit flags to describe the entry
        self.flags = 0x0
        # 1 byte - the storage method of the data
        self.method = None
        # 2 bytes - the size of the name
        #self.nsize - a derived property function
        # 4 bytes - the size crc of the actual data, not the payload
        #self.crc - a derived property function
        # 4 bytes - the size of the compressed data
        #self.csize - a derived property function
        # 4 bytes - the size of the decompressed data
        #self.dsize - a derived property function
        # 4 bytes - the size of the payload data
        #self.psize - a derived property function
        # N bytes - the name of the entry
        self.name = ""

        #################
        # Payload
        #
        # Goes directly into the image, create from the cdata/ddata
        # N bytes - the payload data
        self.pdata = None

        ################
        # End   Format #
        ################

        #################
        # The Data
        # N bytes - the decompressed data
        self.ddata = None
        # N bytes - the compressed data
        self.cdata = None

        #################
        # Image components
        # 8 bytes - the bytearray header core
        self.hdrc = None
        # N bytes - the bytearray header extended
        self.hdre = None
        # N bytes - the bytearray payload data
        #self.pdata = None - defined in the payload section above
        # N bytes - the fully assembled image
        #self.idata - a derived property function

        #################
        # Extended Info
        # Define the entry to a fixed size
        # If set on creation, used to write out the file
        # If the flag is set on read, this variable is set to the payload size
        self.fixed_size = None
        # Track where the entry starts when read from a file
        # This is purely useful extra debug info to compare against a file
        self.offset = None
        # The hash value for this entry, created by calling hash()
        # This is not part of the pak spec, instead a convenience feature
        # to assist in the creation of a hash.list file that can go into the pak
        self.hashvalue = None

    # The property functions for the derived values
    @property
    def hesize(self):
        # 20 is the number of fixed bytes in the extended header
        return self.align(20 + self.nsize)

    @property
    def nsize(self):
        return len(self.name)

    @property
    def csize(self):
        return len(self.cdata)

    @property
    def dsize(self):
        return len(self.ddata)

    @property
    def psize(self):
        return len(self.pdata)

    @property
    def crc(self):
        return zlib.crc32(self.ddata)

    @property
    def idata(self):
        '''
        This property assumes the build function has previously been called
        to generate the values for the PAK_FILE case
        PAK_PAD does not require a build call
        '''
        if (self.magic == PAK_FILE):
            return (self.hdrc + self.hdre + self.pdata)
        elif (self.magic == PAK_PAD):
            return self.magic.to_bytes(4, 'big') + self.padsize.to_bytes(4, 'big') + bytes(self.padsize)

        # We should never get here, raise if we do
        raise ArchiveError("Unknown magic '%s' in idata call!" % self.magic.to_bytes(4, 'big').decode())

    @property
    def isize(self):
        return len(self.idata)

    @property
    def is_pad(self):
        return self.magic == PAK_PAD

    def packHdrc(self):
        '''
        Create the bytearray hdrc data that can be written
        '''
        # magic - 4 bytes
        # version - 2 bytes
        # hesize - 2 bytes
        self.hdrc = struct.pack('>IHH', self.magic, self.version, self.hesize)

        return

    def unpackHdrc(self, i_hdrc):
        '''
        Decode the bytearray hdrc data into the variables we can use
        '''
        # Save original value passed in, would get updated with a call to build
        self.hdrc = i_hdrc

        # Any @property variables are unpacked into local vars for use
        # magic - 4 bytes
        # version - 2 bytes
        # hesize - 2 bytes
        self.magic, self.version, l_hesize = struct.unpack('>IHH', i_hdrc)

        # Error checks
        if self.magic != PAK_FILE:
            raise ArchiveError("Unable to unpack hdrc, invalid magic: 0x%08X!" % self.magic)

        # Only 1 version for now, direct check
        if self.version != PAK_VERSION:
            raise ArchiveError("Unable to unpack hdrc, invalid version: %d!" % self.version)

        return (l_hesize)

    def packHdre(self):
        '''
        Create the bytearray hdre data that can be written
        '''
        # flags - 1 byte
        # method - 1 byte
        # nsize - 2 bytes
        # crc - 4 bytes
        # csize - 4 bytes
        # dsize - 4 bytes
        # psize - 4 bytes
        self.hdre = struct.pack('>BBHIIII', self.flags, self.method, self.nsize,
                                self.crc, self.csize, self.dsize, self.psize)
        # name - n bytes
        self.hdre += self.name.encode()
        # Add alignment data
        self.hdre += bytes(self.hesize - len(self.hdre))

        return

    def unpackHdre(self, i_hdre):
        '''
        Decode the bytearray hdrc data into the variables we can use
        '''
        # Save original value passed in, would get updated with a call to build
        self.hdre = i_hdre

        # Any @property variables are unpacked into local vars for use
        # flags - 1 byte
        # method - 1 byte
        # nsize - 2 bytes
        self.flags, self.method, l_nsize = struct.unpack('>BBH', i_hdre[0:4])
        # Force the method into the enum
        self.method = CM(self.method)

        # crc - 4 bytes
        # csize - 4 bytes
        # dsize - 4 bytes
        # psize - 4 bytes
        l_crc, l_csize, l_dsize, l_psize = struct.unpack('>IIII', i_hdre[4:20])
        # Name field
        self.name = i_hdre[20:(20 + l_nsize)].decode('utf-8')

        return (l_crc, l_csize, l_dsize, l_psize)

    def packPayload(self):
        '''
        Handle compression of the data and then create
        the bytearray payload data that can be written
        '''
        # Set the level of zlib compression based on the method
        # Also use it as an indicator to flow through zlib code path
        zlibLevel = None
        zdata = None

        # Set the compression level based on method
        if self.method == CM.zlib:
            # For default zlib we want max compression
            zlibLevel = 9
            zdata = self.ddata
        if self.method == CM.zlib_fast:
            # In fast, pack a medium level of compression tilted towards speed
            zlibLevel = 5
            zdata = self.ddata
        if self.method == CM.zlib_ppc:
            zlibLevel = 9
            # Do an extra layer of data prep on ppc instructions
            zdata = self.powerpc_filter(self.ddata, True)

        # First try to compress the data if set
        if zlibLevel is not None:
            compressor = zlib.compressobj(level=zlibLevel, wbits=-15)
            self.cdata = compressor.compress(zdata) + compressor.flush(zlib.Z_FINISH)

            # If the compressed data is larger than the original data, just store that
            if len(self.cdata) >= len(self.ddata):
                self.method = CM.store

        # If the entry was originally store or the decompress turned it on
        if self.method == CM.store:
            self.cdata = self.ddata

        # Calculate the payload size
        # If a fixed_size is given, use that
        # Otherwise, just pad out to 8B for alignment
        if (self.fixed_size):
            # Make sure fixed_size isn't smaller than the data
            # If not checked for, the cdata would force the pdata larger and have bad downstream effects
            if (self.fixed_size < self.csize):
                raise ArchiveError("On %s, given size: 0x%X smaller than data size: 0x%X" % (self.name, self.fixed_size, self.csize))
            self.pdata = bytearray(self.fixed_size)
        else:
            self.pdata = bytearray(self.align(self.csize))

        # Insert the data
        self.pdata[0:self.csize] = self.cdata

        return

    def unpackPayload(self, i_pdata, i_crc, i_csize, i_dsize):
        '''
        Uncompress the payload data and set the proper internal variables
        '''
        # Save original value passed in, would get updated with a call to build
        self.pdata = i_pdata

        # Get out the compresssed data
        self.cdata = i_pdata[:i_csize]
        if (self.method in [CM.zlib, CM.zlib_fast, CM.zlib_ppc]):
            self.ddata = zlib.decompress(self.cdata, -15, i_csize)
        else:
            self.ddata = i_pdata[:i_dsize]

        # If zlib_ppc compressed, do an extra layer of unwinding
        if self.method == CM.zlib_ppc:
            self.ddata = self.powerpc_filter(self.ddata, False)

        # Validate the data is valid
        if zlib.crc32(self.ddata) != i_crc:
            raise ArchiveError("File %s is corrupted, CRC mismatch" % self.name)

        # If the fixed size flag was on, save that away
        if (self.flags & PAK_FLAG_FIXED_SIZE):
            self.fixed_size = len(i_pdata)

        return

    def powerpc_filter(self, i_data, i_encode):
        '''
        Optimization for ppc instruction compression
        '''
        uint32be_t = struct.Struct(">I")
        retdata = bytearray(i_data)
        for offset in range(0, len(retdata) & ~3, uint32be_t.size):
            value = uint32be_t.unpack_from(retdata, offset)[0]
            if (value & 0xFC000003) == 0x48000001:
                if i_encode:
                    value = ((value + offset) & 0x03FFFFFC) | 0x48000001
                else:
                    value = ((value - offset) & 0x03FFFFFC) | 0x48000001
                uint32be_t.pack_into(retdata, offset, value)

        return retdata

    def build(self):
        '''
        Trigger all the functions required to build a complete image to write
        Also useful to update entry state
        '''
        # Build the on disk image for the PAK_FILE
        # Nothing to do for PAK_PAD - the idata assembly does that automatically
        if (self.magic == PAK_FILE):
            # Do them in reverse layout order because they inform the prior data segment
            self.packPayload()
            self.packHdre()
            self.packHdrc()

        return

    def ingest(self, i_name, i_method, i_data, i_size=None, i_flags=0x0):
        '''
        Used by build from manifest to ingest the critical info for an entry
        '''
        # Set some base values from data read in and then build to fill in the rest
        self.name = i_name
        self.method = i_method
        self.ddata = i_data
        if i_size:
            self.fixed_size = i_size
            self.flags |= PAK_FLAG_FIXED_SIZE
        self.flags |= i_flags
        self.build()

        return

    def hash(self, i_algorithm="sha3_512", i_version=1):
        '''
        Generate the hash value for this archive entry

        Note: this is not part of the pak spec, just a convenience feature for
        hash.list file creation
        '''
        # The version is completely unused at this point, just provided for the future
        if (i_version != 1):
            raise ArchiveError("Unknown version '%d' given!" % i_version)
        if (i_algorithm != "sha3_512"):
            raise ArchiveError("Unknown algorithm '%s' given!" % i_algorithm)

        # Hash the data
        hasher = hashlib.new(i_algorithm)
        hasher.update(self.cdata)
        # Insert the name length in 2 bytes, then the name itself and finally the hash value
        self.hashvalue = len(self.name).to_bytes(2, 'big')
        self.hashvalue += self.name.encode()
        self.hashvalue += hasher.digest()

        return

    def display(self):
        '''
        Display debug data about the entry
        '''
        # The offset may be set if the archive has gone through the build process or been freshly read in
        # It is not guaranteed to be set though, so print a good indicator when it is not
        if (self.offset != None):
            offset = "0x%06X" % self.offset
        else:
            offset = "N/A"
        if (self.magic == PAK_FILE):
            out.print(self.name)
            # Display useful info like the compression ratio
            try:
                ratio = (self.dsize/self.csize)
            except ZeroDivisionError:
                ratio = 0
            out.print("  size: %6d, flags: 0x%02X, hesize: %2d, nsize: %2d, method: %9s, crc: %08X, csize: %6d: dsize: %6d: ratio: %5.1fx, psize: %6d, offset: %s" %
                     (self.isize, self.flags, self.hesize, self.nsize, self.method, self.crc, self.csize, self.dsize, ratio, self.psize, offset))
        elif (self.magic == PAK_PAD):
            out.print(self.name + "|<pad>|")
            out.print("  size: %d, offset: %s" % (self.padsize, offset))
        else:
            raise ArchiveError("Unknown magic '%s' in display!" % self.magic.to_bytes(4, 'big').decode())

        return

    def align(self, value):
        '''
        Helper function to 8B align data
        '''
        result = value
        if (value & 0x7):
            result = value + (8 - (value & 0x7))

        return result

class Archive(UserList):
    '''
    The class representing the archive to be created
    '''
    def __init__(self, filename=None):
        super().__init__()
        # The file to use when load is invoked or to write to for save
        # Optionally given at creation, can also be set in the load/save functions
        self.filename = filename
        # The contents of file from a load or the in memory image to write on save
        self.image = bytearray()
        # Does the pak have an end marker
        self.end_marker = True

    def _validate_append(self, add):
        '''
        Override list append functions to prevent duplicate addition of the same file
        When a duplicate is found, instead replace it with the new entry at the same location
        This checking does not apply to pads, which can be inserted multiple times
        '''
        if (add.magic == PAK_FILE) and any((add.name == x.name) for x in self.data):
            self.data = [add if add.name == x.name else x for x in self.data]
        else:
            self.data.append(add)

    def append(self, add):
        '''
        Override list append and send through the validated append
        '''
        self._validate_append(add)

    def extend(self, adds):
        '''
        Override list extend and send through the validated append
        '''
        for add in adds:
            self._validate_append(add)

    def __add__(self, adds):
        '''
        Override list + operator and send through the validated append
        '''
        for add in adds:
            self._validate_append(add)
        return self

    def __iadd__(self, adds):
        '''
        Override list += operator and send through the validated append
        '''
        for add in adds:
            self._validate_append(add)
        return self

    def remove(self, entry):
        '''
        Remove the entry either by name or direct object match

        --------
        Remove is a normal list function that has its behavior modified depending on input
        If the input is a string, it assumes the user is trying to remove by entry name
        Otherwise, it tries to do a normal list remove of the entry passed in.
        '''
        # If the entry is a str, match that against the name field
        if type(entry) == str:
            rdata = [keep for keep in self.data if keep.name != entry]
            # If they are the same length, we didn't remove anything - let the user know
            if len(rdata) == len(self.data):
                raise ArchiveError("'%s' not found in archive, remove failed!" % entry)
            # It worked, assign the new smaller list
            self.data = rdata
        else:
            # Try the default list remove
            self.data.remove(entry)

    def add(self, name, method, data):
        '''
        Add a file to the archive
        '''
        # This handles creating the underlying entry for the user
        # It does flow through append to ensure we don't duplicate something
        entry = ArchiveEntry()
        entry.ingest(name, method, data)
        self.append(entry)

    def addPad(self, i_padsize):
        '''
        Add a pad to the archive

        This is the overall size of the pad to add.  Accounting for header,
        etc.. space is accounted for in the function.
        '''
        # This handles creating the underlying entry for the user
        # It does flow through append to ensure we don't duplicate something
        entry = ArchiveEntry(i_type=PAK_PAD)
        entry.padsize = i_padsize - 8 # PAK_PAD + 4 bytes of pad size
        entry.build()
        self.append(entry)

    def extract(self, name):
        '''
        Return the uncompressed contents of the entry specified by name
        '''
        # First find it
        result = self.find(name)

        # No result, throw an error
        if not result:
            raise ArchiveError("File '%s' not found for extact!" % (name))

        # Too many matches to name, throw an error
        if len(result) > 1:
            raise ArchiveError("%d matches for name '%s' found!  Only 1 allowed." % (len(result), name))

        # Return the data
        return result[0].ddata

    def find(self, patterns, include_dirs=True):
        '''
        Search the archive for names matching patterns and return them
        '''
        if not patterns:
            return self

        # If the input patterns is a string, recast as a single value in list
        # Otherwise below it will be gone through character by character
        if type(patterns) == str:
            patterns = [patterns]

        # Search for it
        result = Archive()
        all_names = [e.name for e in self]
        for pattern in patterns:
            # Load all the names into a list for fnfilter to search
            found_names = set(fnmatch.filter(all_names, pattern) + (fnmatch.filter(all_names, pattern + "/*") if include_dirs else []))
            # If we found nothing, raise an error, otherwise add to the returned result
            if not found_names:
                raise ArchiveError("No files matching '%s' found in archive" % pattern)
            else:
                result.extend([e for e in self if e.name in found_names])

        return result

    def createHashList(self, i_algorithm="sha3_512"):
        '''
        For all entries that have a hash value defined, create a hash list entry
        '''
        contents = bytearray()
        # A simple 2 byte header on the hash list
        # 1st byte - file version.  Good for layout changes.
        fversion = 1
        contents += fversion.to_bytes(1, 'big')

        # 2nd byte - algorithm version.  Indicate what algorithm is in use
        if (i_algorithm == "sha3_512"):
            aversion = 1
        else:
            raise ArchiveError("Unknown algoritm '%s' given!" % i_algorithm)
        contents += aversion.to_bytes(1, 'big')

        # Now create all the entries
        for entry in self:
            if entry.hashvalue:
                contents += entry.hashvalue

        # Tack a 0000 onto the end of the file
        # This is especially useful when the 'file' is being read in memory
        # Instead of eof(), the 0000 indicates end of data and also a valid length of 0
        contents += bytes(2)

        return contents

    def load(self, filename=None, image=None):
        '''
        Load the given archive and process it into the ArchiveEntry classes

        The given archive can be either a filename to open or an already loaded archive image
        '''

        # If the filename was given at load call, set the internal variable
        if (filename):
            self.filename = filename

        # Make sure both weren't given
        if (self.filename and image):
            raise ArchiveError("Both filename and image can't be given for load!")

        # No conflict, load the right one into the local image
        if image:
            # Real simple - assign the passed in image to the internal archive image for processing
            self.image = image
        else:
            # See if the input archive already exists as a file
            # If it doesn't, throw an error.. maybe make that supressable
            if not os.path.isfile(self.filename):
                out.error("The given archive file \'%s\' does not exist!" % self.filename)
                return None

            # Read the entire file into the image for reference
            with open(self.filename, "rb") as f:
                self.image = f.read()

        # Assume a load of an existing archive will not have the end marker
        # If it does, we will catch that in the processing and set the indicator
        # This will preserve that value across archive operations
        self.end_marker = False

        # Loop through bytearray image in memory and pull out the data
        offset = 0
        while (offset < len(self.image)):
            # Check for the start or end marker before trying to process
            if (int.from_bytes(self.image[offset:(offset + 4)], 'big') == PAK_FILE):
                # Create the entry we are going to fill in
                entry = ArchiveEntry(i_type=PAK_FILE)

                # Unpack the hdrc block
                readsz = 8
                l_hesize = entry.unpackHdrc(self.image[offset:(offset + readsz)])
                offset += readsz

                # Unpack the hdre block
                readsz = l_hesize
                (l_crc, l_csize, l_dsize, l_psize) = entry.unpackHdre(self.image[offset:(offset + readsz)])
                offset += readsz

                # Unpack the payload
                readsz = l_psize
                entry.unpackPayload(self.image[offset:(offset + readsz)], l_crc, l_csize, l_dsize)
                offset += readsz
            elif (int.from_bytes(self.image[offset:(offset + 4)], 'big') == PAK_PAD):
                # Advance the magic we just read
                offset += 4

                # Create the entry we are going to fill in
                entry = ArchiveEntry(i_type=PAK_PAD)

                # Fill in the pad length from the other 4 bytes
                readsz = 4
                entry.padsize = int.from_bytes(self.image[offset:(offset + readsz)], 'big')
                offset += readsz

                # Advance the length of the pad size
                offset += entry.padsize
            elif (int.from_bytes(self.image[offset:(offset + 4)], 'big') == PAK_END):
                # Hit the end, get out of here
                self.end_marker = True
                break
            else:
                print('%x' % int.from_bytes(self.image[offset:(offset + 4)], 'big'))
                raise ArchiveError("Unknown magic block found at offset: %d" % offset)

            # The entry is created without error, add it to the list
            self.append(entry)

        return

    def build(self):
        '''
        Build the image that will be written out

        This archive level build assumes the entry level build has already been done
        This will grab the pre-existing idata in each entry to build the full archive image
        '''
        # Build the full image from all the parts
        self.image = bytearray()
        offset = 0
        for entry in self:
            entry.offset = offset
            self.image += entry.idata
            offset += entry.isize

        # Add the end marker if requested
        if self.end_marker:
            # First 4 bytes are the end magic
            self.image += PAK_END.to_bytes(4, 'big')
            # Last 4 bytes are the total length of the archive
            self.image += (len(self.image) + 4).to_bytes(4, 'big')

    def save(self, filename=None):
        '''
        Write out the ArchiveEntry information into a useable archive
        '''
        # All the passing in of the filename to save to
        if (filename):
            self.filename = filename

        # Make sure filename to save to is specified
        if (self.filename == None):
            raise ArchiveError("filename to save to not specified!")

        # Rebuild the full archive, including the image to be written out
        self.build()

        # We've got the image, write it out
        with open(self.filename, "wb") as f:
            f.write(self.image)

##############################
# All manifest related info
##############################
class Manifest(object):
    '''
    Store the syntax validated version of the input manifest dict
    '''
    def __init__(self):
        # The compression level
        self.method = CM.zlib
        # Add in the end marker
        self.end_marker = True
        # A hashfile to put hashes in to
        self.hashfile = None
        # The list of layout entries
        self.layouts = list()

    def to_dict(self):
        '''
        First attempt at function to turn the manifest class back into a dictionary
        Would be useful to write out the fully resolved manifest that matches the created archive
        It works, but needs some major work
        '''
        # Main dict and top sections
        d = dict()
        d["global"] = dict()
        d["layout"] = dict()

        # Load in each sub section
        # Globals
        if self.method != None:
            d["global"]["method"] = self.method.name
        if self.end_marker != None:
            d["global"]["end-marker"] = self.end_marker
        if self.hashfile != None:
            d["global"]["hashfile"] = self.hashfile

        # Layout
        for layout in self.layouts:
            d["layout"][layout.name] = dict()
            if layout.file != None:
                d["layout"][layout.name]["file"] = layout.file
            if layout.directory != None:
                d["layout"][layout.name]["directory"] = layout.directory
            if layout.pattern != None:
                d["layout"][layout.name]["pattern"] = layout.pattern
            if layout.method != None:
                d["layout"][layout.name]["method"] = layout.method.name
            if layout.location != None:
                d["layout"][layout.name]["location"] = layout.location
            if layout.size != None:
                d["layout"][layout.name]["size"] = layout.size
            if layout.hash != None:
                d["layout"][layout.name]["hash"] = layout.hash

        return d

    def parse(self, manifestFile):
        '''
        Opens, parses and fully validates a .manifest file
        '''
        errors = 0

        # Open the file, parse it and eval it into the dictionary 'data'
        # Any error is a hard return of the program as we at least need a valid data struct
        with open(manifestFile, "r") as f:
            out.print("Validating manifest syntax")
            # First make sure we can parse the manifest - proper braces, commas, etc..
            try:
                parsedata = ast.parse(f.read(), mode="eval")
            except SyntaxError as e:
                out.critical("Syntax error parsing manifest, line %d. Entry: '%s'" % (e.lineno, e.text.strip()))
                out.critical("Hint - The actual error may be on an earlier line.")
                return 1

            # Now validate all the values are at least valid python expression
            # For example, True and not a typo of Tru
            try:
                data = ast.literal_eval(parsedata)
            except ValueError as e:
                # Get the error data, both the message and location
                exc_type, exc_value, exc_traceback = sys.exc_info()
                # First the error message
                out.critical("%s" % (exc_value))
                # Now get the line number and position
                last_tb = exc_traceback
                while last_tb.tb_next:
                    last_tb = last_tb.tb_next
                out.critical("Found at location: line=%d, col=%d" % (last_tb.tb_frame.f_locals["node"].lineno,
                                                                     last_tb.tb_frame.f_locals["node"].col_offset))
                return 1

        ################################################
        # Validate the values read in

        # Instead of just getting the values we need, instead loop through all values read in
        # This will allow us to check for anything invalid added by the user
        out.print("Validating 'global' keyword values")
        for key, value in data["global"].items():
            if (key == "method"):
                self.method = CM[value]
            elif (key == "end-marker"):
                self.end_marker = value
            elif (key == "hashfile"):
                self.hashfile = value
            else:
                out.error("global keyword '%s' not known!" % key)
                errors += 1

        # We don't care where the hashfile goes, we just want it named "hash.list" for consistency
        if self.hashfile and not self.hashfile.endswith("hash.list"):
            out.error("Your hashfile is named '%s'" % self.hashfile)
            out.error("Convention requires the file be named 'hash.list'")
            out.error("The directory does not matter, just the name")
            errors += 1

        # Now validate all the layout keywords in the same method
        out.print("Validating 'layout' keyword values")
        for key, value in data["layout"].items():
            entry = ManifestLayout()
            entry.name = key
            # Set the default from the manifest
            entry.method = self.method
            # Set the default based on hashfile existence
            entry.hash = True if self.hashfile else False

            # Make sure every key given for the layout is valild
            for subkey, subvalue in value.items():
                if (subkey == "method"):
                    entry.method = CM[subvalue]
                elif (subkey == "file"):
                    entry.file = subvalue
                elif (subkey == "directory"):
                    entry.directory = subvalue
                elif (subkey == "pattern"):
                    entry.pattern = subvalue
                elif (subkey == "location"):
                    entry.location = subvalue
                elif (subkey == "size"):
                    entry.size = subvalue
                elif (subkey == "hash"):
                    entry.hash = subvalue
                else:
                    out.error("layout keyword '%s' in file '%s' not known!" % (subkey, key))
                    errors += 1

            # Done with our key validation, now make sure we got the right info to build an entry
            if (entry.file and entry.directory):
                out.error("Found both a \'file\' and \'directory\' entry for layout '%s'" % key)
                errors += 1
                continue

            if (not (entry.file or entry.directory)):
                out.error("Found neither a \'file\' or \'directory\' entry for layout '%s'" % key)
                errors += 1
                continue

            if (entry.directory and not entry.pattern):
                out.error("A keyword 'pattern' required to be used with a directory entry")
                errors += 1
                continue

            # Make sure hash is just a True/False
            if entry.hash not in [True, False]:
                out.error("Invalid value for 'hash' in entry for layout '%s'" % key)
                out.error("Only 'True' or 'False' are valid")
                errors += 1
                continue

            # If hash generation is enabled, make sure a hash file is given
            if entry.hash and not self.hashfile:
                out.error("global hashfile not given, but hash creation enabled for layout '%s'" % key)
                errors += 1
                continue

            # Stick the class into the list
            self.layouts.append(entry)

        # All done, return the total count of parsing errors encountered
        return errors


    def build(self, basepath=None):
        '''
        Build out the manifest using the basepath and searching for files in the directory entries
        '''
        errors = 0
        newLayouts = list()

        out.print("Building manifest paths")

        for layout in self.layouts:
            # Do directory entries
            # Walk everything under and see how it matches against the patterns provided
            if layout.directory:
                # Track if we find something valid in the directory
                found = False
                # Build the full directory path by joining with the base path
                if (basepath):
                    fdirectory = os.path.join(basepath, layout.directory)
                else:
                    fdirectory = layout.directory
                if (os.path.isdir(fdirectory)):
                    for walkroot, walkdir, walkfiles in os.walk(fdirectory):
                        for pat in layout.pattern:
                            for f in fnmatch.filter(walkfiles, pat):
                                # We found a match, create a new layout entry to load into the final
                                lnew = ManifestLayout()
                                lnew.name = os.path.join(layout.name, f)
                                lnew.method = layout.method
                                lnew.file = os.path.join(walkroot, f)
                                newLayouts.append(lnew)
                                found = True
                # If nothing valid was found, flag it for the user - safe to assume they meant to find something
                if not found:
                    errors += 1
                    out.error("For layout entry '%s', the directory '%s' had no matches for the pattern '%s'" % (layout.name, layout.directory, layout.pattern))

            # If it's an individual file layout, do some simple check and expand the file name
            elif layout.file:
                # Build the full file name (ffile), if basepath was given
                if (basepath):
                    ffile = os.path.join(basepath, layout.file)
                else:
                    ffile = layout.file
                # Add if the file exists, otherwise throw an error for the user
                if os.path.isfile(ffile):
                    layout.file = ffile
                    newLayouts.append(layout)
                else:
                    errors += 1
                    out.error("For layout entry '%s', the file is not found '%s'" % (layout.name, layout.file))

            # Catch all for unhandled cases, should never get there
            else:
                errors += 1
                out.error("For layout entry '%s', unknown layout type!" % (layout.name))

        # All done, replace the original layouts with the new layouts
        self.layouts = copy.deepcopy(newLayouts)

        return errors

    def createArchive(self):
        '''
        Build an archive object from the layout data
        '''
        # The archive object to build and return
        archive = Archive()

        # With everything fully resolved, go through all the layout entries and create archive entries
        for layout in self.layouts:
            with open(layout.file, "rb") as f:
                entry = ArchiveEntry()
                entry.ingest(layout.name, layout.method, f.read(), i_size=layout.size)
                # If hash was enabled for this layout, also trigger that creation
                if layout.hash:
                    entry.hash()
                archive.append(entry)

        # If hashfile is enabled, create the hash list and stick it into the archive
        if self.hashfile:
            contents = archive.createHashList()
            archive.add(self.hashfile, CM.zlib, contents)

        # Set the archive end_marker value to the manifest value
        archive.end_marker = self.end_marker

        return archive

class ManifestLayout(object):
    '''
    Store the manifest dict entries after processing/validation
    '''
    def __init__(self):
        # The name to use in the archive
        self.name = None
        # The file to insert into the archive (maybe actually the contents??)
        self.file = None
        # The directory and pattern to look for
        self.directory = None
        self.pattern = None
        # The method of compression
        self.method = None
        # The fixed location in the archive the data should be placed
        self.location = None
        # The fixed size in the archive
        self.size = None
        # Create a hash entry in the hash file
        self.hash = None
