#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
#    Copyright (C) 2012  Juan Martín <android@nauj27.com>
#
#    This program can be distributed under the terms of the GNU GPL v3.
#    See the file COPYING.
#
#    v0.1-alpha-wip
#

import os
import stat
import errno
import subprocess

import fuse
from fuse import Fuse
from datetime import datetime

# TODO: it should be a parameter
FILE_CACHE_TIMEOUT = 60 # in seconds
DIR_CACHE_TIMEOUT = 180 # in seconds

if not hasattr(fuse, '__version__'):
    raise RuntimeError(\
    "your fuse-py doesn't know of fuse.__version__,\probably it's too old.")

fuse.fuse_python_api = (0, 2)

class MyStat(fuse.Stat):

    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0


class FileData(object):

    def __init__(self, name, attr):
        self.name = name           # File name
        self.attr = attr           # MyStat object
        self.time = datetime.now() # Creation of the File object

    def is_recent(self):
        return (datetime.now() - self.time).seconds < FILE_CACHE_TIMEOUT


class DirectoryData(object):

    def __init__(self, name, content):
        self.name = name           # Directory name
        self.content = content     # Directory content
        self.time = datetime.now() # Creation of the object

    def is_recent(self):
        return (datetime.now() - self.time).seconds < DIR_CACHE_TIMEOUT


class AdbFuse(Fuse):

    def __init__(self, *args, **kw):
#        self.home = os.path.expanduser('~')
#        self.cache = '%s/.adbfuse' % (self.home, )
#        if not os.path.isdir(self.cache):
#            os.makedirs(self.cache)
            
        self.dirs = {}
        self.files = {}
        fuse.Fuse.__init__(self, *args, **kw)

    def getattr(self, path):
        #print "DEBUG -- getattr with path %s" % path

        # Search for data in the files cache data
        if self.files.has_key(path):
            fileData = self.files[path]
            if fileData.is_recent():
                if path.endswith('hello.py'):
                    print "File size: %d" % (fileData.attr.st_size, )
                return fileData.attr

        # There are not cache data or cache data is too old
        print "DEBUG -- getattr with path %s" % path
        myStat = MyStat()

        if path == '/':
            myStat.st_mode = stat.S_IFDIR | 0755
            myStat.st_nlink = 2
        else:
            process = subprocess.Popen(
                ['adb', 'shell', 'stat', '-t', '""%s""' % path],
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
            )
            (out_data, err_data) = process.communicate()
            #import pdb; pdb.set_trace()

            # remove the path from the output string
            out_data = out_data[len(path)+1:]
            out_data_array = out_data.split()

            if (len(out_data_array) == 14):
                myStat.st_size = int(out_data_array[0])
                myStat.st_mode = int(out_data_array[2], 16)
                myStat.st_uid = int(out_data_array[3])
                myStat.st_gid = int(out_data_array[4])
                myStat.st_dev = int(out_data_array[5], 16)
                myStat.st_ino = int(out_data_array[6])
                myStat.st_nlink = int(out_data_array[7])
                myStat.st_atime = int(out_data_array[10])
                myStat.st_mtime = int(out_data_array[11])
                myStat.st_ctime = int(out_data_array[12])

            else:
                return -errno.ENOENT

        self.files[path] = FileData(path, myStat)
        return myStat

    def readdir(self, path, offset):
        # Use cache if possible
        if self.dirs.has_key(path):
            directoryData = self.dirs[path]
            if directoryData.is_recent():
                for r in directoryData.content:
                    yield fuse.Direntry(r)
                return

        # There is no cache data of cache data is not recent
        print "DEBUG -- readdir with path %s and offset %s" % (path, offset, )

        process = subprocess.Popen(
            ['adb', 'shell', 'ls', '--color=none', "-1", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out_data, err_data) = process.communicate()

        content = out_data.splitlines()
        self.dirs[path] = DirectoryData(path, content)
        for r in content:
            yield fuse.Direntry(r)

    def open(self, path, flags):
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        print "DEBUG -- read with path %s, size %d and offset %d" % (
            path, size, offset, )

        if self.files.has_key(path):
            fileData = self.files[path]
            if offset < fileData.attr.st_size:
                # Fix size
                if offset + size > fileData.attr.st_size:
                    size = fileData.attr.st_size - offset

                print " ".join(['adb', 'shell', 'dd', 'if="%s"' % (path, ),
                    'skip=%d' % (offset, ), 'bs=1', 'count=%d' % (size, )])

                #'2>', '/dev/null""'],
                # THIS IS BROKEN RIGHT NOW
                # adb shell "dd if=file 2> /dev/null" works like a charm
                # but, how to get it inside Popen??
                # Try check_output, only for python >= 2.7.x - not for debian 6 :(
                # fu = subprocess.check_call(
                #       ['adb', 'shell', 'dd', 'if=/mnt/sdcard/j/he llo', '2>', '/dev/null'])
                process = subprocess.call(
                    ['adb', 'shell', 'dd', 'if=%s' % (path, ),
                    'skip=%d' % (offset, ), 'bs=1', 'count=%d' % (size, )])
                (out_data, err_data) = process.communicate()
                import pdb; pdb.set_trace()
                
                # Remove the dd tail status lines
                returned_data = out_data.splitlines(True)[:-3]
                rawdata = ''.join(returned_data)
            else:
                rawdata = ''
        else:
            rawdata = '' 

        print "Returning %d bytes" % (len(rawdata), )
        return rawdata
            
    def readlink(self, path):
        process = subprocess.Popen(
            ['adb', 'shell', 'readlink', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out_data, err_data) = process.communicate()

        target = out_data.split()[0]
        if target.startswith('/'):
            return '.%s' % (target, )
        else:
            return '%s' % (target, )

    def unlink(self, path):
        process = subprocess.Popen(
            ['adb', 'shell', 'rm', '-f', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def rmdir(self, path):
        process = subprocess.Popen(
            ['adb', 'shell', 'rmdir', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def symlink(self, path, path1):
        process = subprocess.Popen(
            ['adb', 'shell', 'ln', '-s', path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def rename(self, path, path1):
        process = subprocess.Popen(
            ['adb', 'shell', 'mv', "." + path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def link(self, path, path1):
        process = subprocess.Popen(
            ['adb', 'shell', 'ln', "." + path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def chmod(self, path, mode):
        process = subprocess.Popen(
            ['adb', 'shell', 'chmod', "." + path, mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def chown(self, path, user, group):
        process = subprocess.Popen(
            ['adb', 'shell', 'chown', "." + path, user, group],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def mknod(self, path, mode, dev):
        #print "*** path: %s, mode: %s, dev: %s" % (path, mode, dev,)
        process = subprocess.Popen(
            #['adb', 'shell', 'mknod', "-m", mode, '".' + path + '"', dev],
            ['adb', 'shell', 'touch', '.' + path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def mkdir(self, path, mode):
        process = subprocess.Popen(
            ['adb', 'shell', 'mkdir', "." + path, mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def utime(self, path, times):
        process = subprocess.Popen(
            ['adb', 'shell', 'touch', "-d", times, "." + path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

def main():
    usage="""
Userspace adb filesystem

""" + Fuse.fusage
    server = AdbFuse(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
