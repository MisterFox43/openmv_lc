#!/usr/bin/env python2
# This file is part of the OpenMV project.
#
# Copyright (c) 2013-2021 Ibrahim Abdelkader <iabdalkader@openmv.io>
# Copyright (c) 2013-2021 Kwabena W. Agyeman <kwagyeman@openmv.io>
#
# This work is licensed under the MIT license, see the file LICENSE for details.
#
# This module implements the DFU protocol for STM32 chips.
# See app note AN3156 for a description of the DFU protocol.
# See document UM0391 for a description of the DFuse file.

from __future__ import print_function

import argparse
import re
import struct
import sys
import usb.core
import usb.util
import zlib
import os
import time

# VID/PID
__VID = 0x0483
__PID = 0xdf11

# USB request __TIMEOUT
__TIMEOUT = 5000

# DFU commands
__DFU_DETACH    = 0
__DFU_DNLOAD    = 1
__DFU_UPLOAD    = 2
__DFU_GETSTATUS = 3
__DFU_CLRSTATUS = 4
__DFU_GETSTATE  = 5
__DFU_ABORT     = 6

# DFU status
__DFU_STATE_APP_IDLE                 = 0x00
__DFU_STATE_APP_DETACH               = 0x01
__DFU_STATE_DFU_IDLE                 = 0x02
__DFU_STATE_DFU_DOWNLOAD_SYNC        = 0x03
__DFU_STATE_DFU_DOWNLOAD_BUSY        = 0x04
__DFU_STATE_DFU_DOWNLOAD_IDLE        = 0x05
__DFU_STATE_DFU_MANIFEST_SYNC        = 0x06
__DFU_STATE_DFU_MANIFEST             = 0x07
__DFU_STATE_DFU_MANIFEST_WAIT_RESET  = 0x08
__DFU_STATE_DFU_UPLOAD_IDLE          = 0x09
__DFU_STATE_DFU_ERROR                = 0x0a

__DFU_STATUS = [
    "DFU_STATE_APP_IDLE",
    "DFU_STATE_APP_DETACH",
    "DFU_STATE_DFU_IDLE",
    "DFU_STATE_DFU_DOWNLOAD_SYNC",
    "DFU_STATE_DFU_DOWNLOAD_BUSY",
    "DFU_STATE_DFU_DOWNLOAD_IDLE",
    "DFU_STATE_DFU_MANIFEST_SYNC",
    "DFU_STATE_DFU_MANIFEST",
    "DFU_STATE_DFU_MANIFEST_WAIT_RESET",
    "DFU_STATE_DFU_UPLOAD_IDLE",
    "DFU_STATE_DFU_ERROR"
]

_DFU_DESCRIPTOR_TYPE                 = 0x21

# USB device handle
__dev = None

__verbose = None

# USB DFU interface
__DFU_INTERFACE = 0

import inspect
if 'length' in inspect.getargspec(usb.util.get_string).args:
    # PyUSB 1.0.0.b1 has the length argument
    def get_string(dev, index):
        return usb.util.get_string(dev, 255, index)
else:
    # PyUSB 1.0.0.b2 dropped the length argument
    def get_string(dev, index):
        return usb.util.get_string(dev, index)


def init():
    """Initializes the found DFU device so that we can program it."""
    global __dev
    devices = get_dfu_devices(idVendor=__VID, idProduct=__PID)
    if not devices:
        raise ValueError('No DFU device found')
    if len(devices) > 1:
        raise ValueError("Multiple DFU devices found")
    __dev = devices[0]

    # Claim DFU interface
    usb.util.claim_interface(__dev, __DFU_INTERFACE)

    # Clear status
    clr_status()

def clr_status():
    """Clears any error status (perhaps left over from a previous session)."""
    while (get_status() != __DFU_STATE_DFU_IDLE):
        __dev.ctrl_transfer(0x21, __DFU_CLRSTATUS, 0, __DFU_INTERFACE, None, __TIMEOUT)
        time.sleep(0.100)


def get_status():
    """Get the status of the last operation."""
    stat = __dev.ctrl_transfer(0xA1, __DFU_GETSTATUS, 0, __DFU_INTERFACE, 6, 20000)
    #print ("DFU Status: ", __DFU_STATUS[stat[4]])
    return stat[4]


def mass_erase():
    """Performs a MASS erase (i.e. erases the entire device."""
    # Send DNLOAD with first byte=0x41
    __dev.ctrl_transfer(0x21, __DFU_DNLOAD, 0, __DFU_INTERFACE,
                        "\x41", __TIMEOUT)

    # Execute last command
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_BUSY:
        raise Exception("DFU: erase failed")

    # Check command state
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_IDLE:
        raise Exception("DFU: erase failed")


def page_erase(addr):
    """Erases a single page."""
    if __verbose:
        print("Erasing page: 0x%x..." % (addr))

    # Send DNLOAD with first byte=0x41 and page address
    buf = struct.pack("<BI", 0x41, addr)
    __dev.ctrl_transfer(0x21, __DFU_DNLOAD, 0, __DFU_INTERFACE, buf, __TIMEOUT)

    # Execute last command
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_BUSY:
        raise Exception("DFU: erase failed")

    # Check command state
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_IDLE:

        raise Exception("DFU: erase failed")


def set_address(addr):
    """Sets the address for the next operation."""
    # Send DNLOAD with first byte=0x21 and page address
    buf = struct.pack("<BI", 0x21, addr)
    __dev.ctrl_transfer(0x21, __DFU_DNLOAD, 0, __DFU_INTERFACE, buf, __TIMEOUT)

    # Execute last command
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_BUSY:
        raise Exception("DFU: set address failed")

    # Check command state
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_IDLE:
        raise Exception("DFU: set address failed")


def write_memory(addr, buf, progress=None, progress_addr=0, progress_size=0):
    """Writes a buffer into memory. This routine assumes that memory has
    already been erased.
    """

    xfer_count = 0
    xfer_bytes = 0
    xfer_total = len(buf)
    xfer_base = addr

    while xfer_bytes < xfer_total:
        if __verbose and xfer_count % 512 == 0:
            print ("Addr 0x%x %dKBs/%dKBs..." % (xfer_base + xfer_bytes,
                                                 xfer_bytes // 1024,
                                                 xfer_total // 1024))
        if progress and xfer_count % 256 == 0:
            progress(progress_addr, xfer_base + xfer_bytes - progress_addr,
                     progress_size)

        # Set mem write address
        set_address(xfer_base+xfer_bytes)

        # Send DNLOAD with fw data
        chunk = min(64, xfer_total-xfer_bytes)
        __dev.ctrl_transfer(0x21, __DFU_DNLOAD, 2, __DFU_INTERFACE,
                            buf[xfer_bytes:xfer_bytes + chunk], __TIMEOUT)

        # Execute last command
        if get_status() != __DFU_STATE_DFU_DOWNLOAD_BUSY:
            raise Exception("DFU: write memory failed")

        # Check command state
        if get_status() != __DFU_STATE_DFU_DOWNLOAD_IDLE:
            raise Exception("DFU: write memory failed")

        xfer_count += 1
        xfer_bytes += chunk


def write_page(buf, xfer_offset):
    """Writes a single page. This routine assumes that memory has already
    been erased.
    """

    xfer_base = 0x08000000

    # Set mem write address
    set_address(xfer_base+xfer_offset)

    # Send DNLOAD with fw data
    __dev.ctrl_transfer(0x21, __DFU_DNLOAD, 2, __DFU_INTERFACE, buf, __TIMEOUT)

    # Execute last command
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_BUSY:
        raise Exception("DFU: write memory failed")

    # Check command state
    if get_status() != __DFU_STATE_DFU_DOWNLOAD_IDLE:
        raise Exception("DFU: write memory failed")

    if __verbose:
        print ("Write: 0x%x " % (xfer_base + xfer_offset))


def exit_dfu():
    """Exit DFU mode, and start running the program."""

    # set jump address
    set_address(0x08000000)

    # Send DNLOAD with 0 length to exit DFU
    __dev.ctrl_transfer(0x21, __DFU_DNLOAD, 0, __DFU_INTERFACE,
                        None, __TIMEOUT)

    try:
        # Execute last command
        if get_status() != __DFU_STATE_DFU_MANIFEST:
            print("Failed to reset device")

        # Release device
        usb.util.dispose_resources(__dev)
    except:
        pass


def named(values, names):
    """Creates a dict with `names` as fields, and `values` as values."""
    return dict(zip(names.split(), values))


def consume(fmt, data, names):
    """Parses the struct defined by `fmt` from `data`, stores the parsed fields
    into a named tuple using `names`. Returns the named tuple, and the data
    with the struct stripped off."""
    size = struct.calcsize(fmt)
    return named(struct.unpack(fmt, data[:size]), names), data[size:]


def cstring(string):
    """Extracts a null-terminated string from a byte array."""
    return string.decode('utf-8').split('\0', 1)[0]


def compute_crc(data):
    """Computes the CRC32 value for the data passed in."""
    return 0xFFFFFFFF & -zlib.crc32(data) - 1


def read_dfu_file(filename):
    """Reads a DFU file, and parses the individual elements from the file.
    Returns an array of elements. Each element is a dictionary with the
    following keys:
        num     - The element index
        address - The address that the element data should be written to.
        size    - The size of the element ddata.
        data    - The element data.
    If an error occurs while parsing the file, then None is returned.
    """

    print("File: {}".format(filename))
    with open(filename, 'rb') as fin:
        data = fin.read()
    crc = compute_crc(data[:-4])
    elements = []

    # Decode the DFU Prefix
    #
    # <5sBIB
    #   <   little endian
    #   5s  char[5]     signature   "DfuSe"
    #   B   uint8_t     version     1
    #   I   uint32_t    size        Size of the DFU file (not including suffix)
    #   B   uint8_t     targets     Number of targets
    dfu_prefix, data = consume('<5sBIB', data,
                               'signature version size targets')
    print ("    %(signature)s v%(version)d, image size: %(size)d, "
           "targets: %(targets)d" % dfu_prefix)
    for target_idx in range(dfu_prefix['targets']):
        # Decode the Image Prefix
        #
        # <6sBI255s2I
        #   <   little endian
        #   6s      char[6]     signature   "Target"
        #   B       uint8_t     altsetting
        #   I       uint32_t    named       bool indicating if a name was used
        #   255s    char[255]   name        name of the target
        #   I       uint32_t    size        size of image (not incl prefix)
        #   I       uint32_t    elements    Number of elements in the image
        img_prefix, data = consume('<6sBI255s2I', data,
                                   'signature altsetting named name '
                                   'size elements')
        img_prefix['num'] = target_idx
        if img_prefix['named']:
            img_prefix['name'] = cstring(img_prefix['name'])
        else:
            img_prefix['name'] = ''
        print('    %(signature)s %(num)d, alt setting: %(altsetting)s, '
              'name: "%(name)s", size: %(size)d, elements: %(elements)d'
              % img_prefix)

        target_size = img_prefix['size']
        target_data, data = data[:target_size], data[target_size:]
        for elem_idx in range(img_prefix['elements']):
            # Decode target prefix
            #   <   little endian
            #   I   uint32_t    element address
            #   I   uint32_t    element size
            elem_prefix, target_data = consume('<2I', target_data, 'addr size')
            elem_prefix['num'] = elem_idx
            print('      %(num)d, address: 0x%(addr)08x, size: %(size)d'
                  % elem_prefix)
            elem_size = elem_prefix['size']
            elem_data = target_data[:elem_size]
            target_data = target_data[elem_size:]
            elem_prefix['data'] = elem_data
            elements.append(elem_prefix)

        if len(target_data):
            print("target %d PARSE ERROR" % target_idx)

    # Decode DFU Suffix
    #   <   little endian
    #   H   uint16_t    device  Firmware version
    #   H   uint16_t    product
    #   H   uint16_t    vendor
    #   H   uint16_t    dfu     0x11a   (DFU file format version)
    #   3s  char[3]     ufd     'UFD'
    #   B   uint8_t     len     16
    #   I   uint32_t    crc32
    dfu_suffix = named(struct.unpack('<4H3sBI', data[:16]),
                       'device product vendor dfu ufd len crc')
    print ('    usb: %(vendor)04x:%(product)04x, device: 0x%(device)04x, '
           'dfu: 0x%(dfu)04x, %(ufd)s, %(len)d, 0x%(crc)08x' % dfu_suffix)
    if crc != dfu_suffix['crc']:
        print("CRC ERROR: computed crc32 is 0x%08x" % crc)
        return
    data = data[16:]
    if data:
        print("PARSE ERROR")
        return

    return elements


class FilterDFU(object):
    """Class for filtering USB devices to identify devices which are in DFU
    mode.
    """

    def __call__(self, device):
        for cfg in device:
            for intf in cfg:
                return (intf.bInterfaceClass == 0xFE and
                        intf.bInterfaceSubClass == 1)


def get_dfu_devices(*args, **kwargs):
    """Returns a list of USB device which are currently in DFU mode.
    Additional filters (like idProduct and idVendor) can be passed in to
    refine the search.
    """
    # convert to list for compatibility with newer pyusb
    return list(usb.core.find(*args, find_all=True,
                              custom_match=FilterDFU(), **kwargs))


def get_memory_layout(device):
    """Returns an array which identifies the memory layout. Each entry
    of the array will contain a dictionary with the following keys:
        addr        - Address of this memory segment
        last_addr   - Last address contained within the memory segment.
        size        - size of the segment, in bytes
        num_pages   - number of pages in the segment
        page_size   - size of each page, in bytes
    """
    cfg = device[0]
    intf = cfg[(0, 0)]
    mem_layout_str = get_string(device, intf.iInterface)
    mem_layout = mem_layout_str.split('/')
    addr = int(mem_layout[1], 0)
    segments = mem_layout[2].split(',')
    seg_re = re.compile(r'(\d+)\*(\d+)(.)(.)')
    result = []
    for segment in segments:
        seg_match = seg_re.match(segment)
        num_pages = int(seg_match.groups()[0], 10)
        page_size = int(seg_match.groups()[1], 10)
        multiplier = seg_match.groups()[2]
        if multiplier == 'K':
            page_size *= 1024
        if multiplier == 'M':
            page_size *= 1024 * 1024
        size = num_pages * page_size
        last_addr = addr + size - 1
        result.append(named((addr, last_addr, size, num_pages, page_size),
                      "addr last_addr size num_pages page_size"))
        addr += size
    return result


def list_dfu_devices(*args, **kwargs):
    """Prints a list of devices detected in DFU mode."""
    devices = get_dfu_devices(*args, **kwargs)
    if not devices:
        print("No DFU capable devices found")
        return
    for device in devices:
        print("Bus {} Device {:03d}: ID {:04x}:{:04x}"
              .format(device.bus, device.address,
                      device.idVendor, device.idProduct))
        layout = get_memory_layout(device)
        print("Memory Layout")
        for entry in layout:
            print("    0x{:x} {:2d} pages of {:3d}K bytes"
                  .format(entry['addr'], entry['num_pages'],
                          entry['page_size'] // 1024))


def write_elements(elements, mass_erase_used, progress=None):
    """Writes the indicated elements into the target memory,
    erasing as needed.
    """

    mem_layout = get_memory_layout(__dev)
    for elem in elements:
        addr = elem['addr']
        size = elem['size']
        data = elem['data']
        elem_size = size
        elem_addr = addr
        if progress:
            progress(elem_addr, 0, elem_size)
        while size > 0:
            write_size = size
            if not mass_erase_used:
                for segment in mem_layout:
                    if addr >= segment['addr'] and \
                       addr <= segment['last_addr']:
                        # We found the page containing the address we want to
                        # write, erase it
                        page_size = segment['page_size']
                        page_addr = addr & ~(page_size - 1)
                        if addr + write_size > page_addr + page_size:
                            write_size = page_addr + page_size - addr
                        page_erase(page_addr)
                        break
            write_memory(addr, data[:write_size], progress,
                         elem_addr, elem_size)
            data = data[write_size:]
            addr += write_size
            size -= write_size
            if progress:
                progress(elem_addr, addr - elem_addr, elem_size)

def write_bin(path, progress=None):
    try:
        with open(path, 'rb') as f:
            buf = f.read()
    except Exception as e:
        print(e)
        return               
    
    xfer_bytes = 0 
    xfer_total = len(buf)
    
    while xfer_bytes < xfer_total:
        # Send chunk
        chunk = min (64, xfer_total-xfer_bytes)
        write_page(buf[xfer_bytes:xfer_bytes+chunk], xfer_bytes)
        xfer_bytes += chunk
        if (progress):
            progress(0x08000000+xfer_bytes, xfer_bytes, xfer_total)

def cli_progress(addr, offset, size):
    """Prints a progress report suitable for use on the command line."""
    width = 25
    done = offset * width // size
    print("\r0x{:08x} {:7d} [{}{}] {:3d}% "
          .format(addr, size, '=' * done, ' ' * (width - done),
                  offset * 100 // size), end="")
    sys.stdout.flush()
    if offset == size:
        print("")


def main():
    """Test program for verifying this files functionality."""
    global __verbose
    # Parse CMD args
    parser = argparse.ArgumentParser(description='DFU Python Util')
    #parser.add_argument("path", help="file path")
    parser.add_argument(
        "-l", "--list",
        help="list available DFU devices",
        action="store_true",
        default=False
    )
    parser.add_argument(
        "-m", "--mass-erase",
        help="mass erase device",
        action="store_true",
        default=False
    )
    parser.add_argument(
        "-u", "--upload",
        help="read file from DFU device",
        dest="path",
        default=False
    )
    parser.add_argument(
        "-v", "--verbose",
        help="increase output verbosity",
        action="store_true",
        default=False
    )
    args = parser.parse_args()

    __verbose = args.verbose

    if args.list:
        list_dfu_devices(idVendor=__VID, idProduct=__PID)
        return

    init()

    if args.mass_erase:
        print ("Mass erase...")
        mass_erase()

    if args.path:
        ext = os.path.splitext(args.path)[1]
        if ext == ".bin":
            print("Writing binary...")
            write_bin(args.path, progress=cli_progress)

            print("Exiting DFU...")
            exit_dfu()
        elif (ext == '.dfu'):
            elements = read_dfu_file(args.path)
            if not elements:
                return
            print("Writing memory...")
            write_elements(elements, args.mass_erase, progress=cli_progress)

            print("Exiting DFU...")
            exit_dfu()
        else:
            print("File format not supported!")

        return

    print("No command specified")

if __name__ == '__main__':
    main()
