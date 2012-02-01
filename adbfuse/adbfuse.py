#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
#    Copyright (C) 2012  Juan Martín <android@nauj27.com>
#
#    This program can be distributed under the terms of the GNU GPL v3.
#    See the file COPYING.
#
#    v0.2-alpha
#

import os
import stat
import time
import errno
import subprocess

import fuse
from fuse import Fuse
from datetime import datetime

# TODO: it should be a parameter
DIR_CACHE_TIMEOUT  = 180          # in seconds
FILE_CACHE_TIMEOUT = 180          # in seconds
DD_BLOCK_SIZE      = 1024
DD_COUNT           = 1024

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
        self.chunkoffset = 0       # Local chunk offset
        self.chunksize = 0         # Local chunk size
        self.refreshing = False

    def is_recent(self):
        return (datetime.now() - self.time).seconds < FILE_CACHE_TIMEOUT

    def contains(self, offset, size):
        return offset >= self.chunkoffset and (offset + size) <= (self.chunkoffset + self.chunksize)
        
    def read_local_cache(self, path, offset, size):
        rawdata = ''
        try:
            rawdata = subprocess.check_output(
                ['dd', 'if=%s' % path, 'skip=%d' % (offset - self.chunkoffset),
                 'bs=1', 'count=%d' % size])
        except subprocess.CalledProcessError:
            pass
        return rawdata
    
    def create_device_cache(self, devicecache, path, offset, bs, count):
        #print "[ADBFUSE][DUMP] dumping cache on device: offset %d, bs %d, count %d" % (offset, bs, count) 
        subprocess.call(
            ['adb', 'shell', 'mkdir', '-p', 
             '%s%s' % (devicecache, path[:path.rfind('/')])])
                
        subprocess.call(
            ['adb', 'shell', 'dd', 'if=%s' % path, 
             'of=%s%s' % (devicecache, path),
             'skip=%d' % (offset / bs), 'bs=%d' % bs, 'count=%d' % count])
    
    def pull(self, devicecache, cache, path):
        #print "[ADBFUSE][PULL] * [PULL] * [PULL] * [PULL] * [PULL] * [PULL] * [PULL] * "
        return_code = subprocess.call(
            ['adb', 'pull', '%s%s' % (devicecache, path),
             '%s%s' % (cache, path)])
        return return_code
                

class DirectoryData(object):

    def __init__(self, name, content):
        self.name = name           # Directory name
        self.content = content     # Directory content
        self.time = datetime.now() # Creation of the object

    def is_recent(self):
        return (datetime.now() - self.time).seconds < DIR_CACHE_TIMEOUT


class AdbFuse(Fuse):

    def __init__(self, *args, **kw):
        # Create the local cache directory
        self.home = os.path.expanduser('~')
        self.cache = '%s/.adbfuse' % (self.home, )
        if not os.path.isdir(self.cache):
            os.makedirs(self.cache)

        # Create if does not exists the remote cache directory
        self.devicecache = '/mnt/asec/.adbfuse'
        subprocess.call(['adb', 'shell', 'mkdir', '-p', '%s' % self.devicecache])
            
        self.dirs = {}
        self.files = {}
        fuse.Fuse.__init__(self, *args, **kw)

    # FIXME: Use pexpect to avoid open a shell eveytime
    def getattr(self, path):
        # Search for data in the files cache data
        if self.files.has_key(path):
            fileData = self.files[path]
            if fileData.is_recent():
                if path == '/':
                    myStat = MyStat()
                    myStat.st_mode = stat.S_IFDIR | 0755
                    myStat.st_nlink = 2
                    return myStat
                else:
                    return fileData.attr

        # There are not cache data or cache data is too old
        myStat = MyStat()
        if path == '/':
            myStat.st_mode = stat.S_IFDIR | 0755
            myStat.st_nlink = 2
        else:
            process = subprocess.Popen(
                ['adb', 'shell', 'stat', '-t', path],
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
            )
            (out_data, err_data) = process.communicate()

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

        # cache outdated or does not exists
        output = subprocess.check_output(['adb', 'shell', 'ls',  '-a','--color=none', "-1", path])
        dirs = output.splitlines()
        self.dirs[path] = DirectoryData(path, dirs)
        
        for dir in dirs:
            yield fuse.Direntry(dir)

    def open(self, path, flags):
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        #print "[ADBFUSE][READ] read(path=%s, size=%d, offset=%d)" % (path, size, offset, )
                
        rawdata = ''
        if self.files.has_key(path):
            fileData = self.files[path]
            
            # check if offset is bigger than file size attribute or
            # file size is zero
            if offset > fileData.attr.st_size or fileData.attr.st_size == 0:
                return ''
            
            # Fix size for reads beyond the file size
            if offset + size > fileData.attr.st_size:
                size = fileData.attr.st_size - offset

            # If there is a chunk in cache check if have valid limits
            if fileData.chunksize != 0 and fileData.contains(offset, size):
                #print "[ADBFUSE][READ] target hit on valid cache"
                rawdata = fileData.read_local_cache('%s%s' % (self.cache, path), offset, size)
            else:
                
                while fileData.refreshing:
                    time.sleep(0.10)
                    fileData = self.files[path]
                    if not fileData.refreshing:
                        rawdata = fileData.read_local_cache('%s%s' % (self.cache, path), offset, size)
                        #print "[ADBFUSE][READ] returning %d bytes delayed" % len(rawdata)
                        return rawdata
                
                # Cache chunk missing or invalid: invalidate fileData chunk
                fileData.chunksize = 0
                fileData.refreshing = True                
                
                # Check if the reader want to read beyond the file size
                if offset + DD_BLOCK_SIZE * DD_COUNT > fileData.attr.st_size:
                    bs = 1
                    #count = size
                    count = fileData.attr.st_size - offset
                else:
                    bs = DD_BLOCK_SIZE
                    count = DD_COUNT
                
                # Slice a chunk from file on the device (tmpfs)
                fileData.create_device_cache(self.devicecache, path, offset, bs, count)
                return_code = fileData.pull(self.devicecache, self.cache, path)

                # If success, get the file chunk from the device
                if return_code == 0:
                    fileData.chunkoffset = offset
                    fileData.chunksize = bs * count
                    fileData.refreshing = False
                    self.files[path] = fileData
                    rawdata = fileData.read_local_cache('%s%s' % (self.cache, path), offset, size)                 

        #print "[ADBFUSE][READ] returning %d bytes" % (len(rawdata), )
        return rawdata
            
    def readlink(self, path):
        target = subprocess.check_output(['adb', 'shell', 'readlink', path]).split()[0]
        
#        if target.startswith('/'):
        return '.%s' % target
#        else:
#            return '%s' % target

    def unlink(self, path):
        subprocess.call(['adb', 'shell', 'rm', '-f', path])

    def rmdir(self, path):
        subprocess.call(['adb', 'shell', 'rmdir', path])

    # TODO: CHECK THIS FUNCTION
    def symlink(self, path, path1):
        print "[ADBFUSE][LINK] symlink(%s, %s)" % (path, path1)
        process = subprocess.Popen(
            ['adb', 'shell', 'ln', '-s', path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    # TODO: CHECK THIS FUNCTION
    def rename(self, path, dstpath):
        #print "[ADBFUSE][RNME] rename(src=%s, dst=%s" % (path, dstpath)
        subprocess.call(['adb', 'shell', 'mv', path, dstpath])
        
        # Force refresh directory cache for parent
        container = path[:path.rfind('/')]
        try:
            self.dirs.pop(container)
        except KeyError:
            pass

    # TODO: CHECK THIS FUNCTION
    def link(self, path, path1):
        process = subprocess.Popen(
            ['adb', 'shell', 'ln', "." + path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    # TODO: CHECK THIS FUNCTION
    def chmod(self, path, mode):
        process = subprocess.Popen(
            ['adb', 'shell', 'chmod', "." + path, mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    # TODO: CHECK THIS FUNCTION
    def chown(self, path, user, group):
        process = subprocess.Popen(
            ['adb', 'shell', 'chown', "." + path, user, group],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def mknod(self, path, mode, dev):
        return -errno.EPERM        

    def mkdir(self, path, mode):
        #print "[ADBFUSE][MKDR] mkdir(path=%s, mode=%s)" % (path, mode)
        subprocess.call(['adb', 'shell', 'mkdir', "-m", "%s" % oct(mode), "-p", path])
        
        # Force refresh directory cache for parent
        container = path[:path.rfind('/')]
        try:
            self.dirs.pop(container)
        except KeyError:
            pass

    def utime(self, path, times):
        #print "[ADBFUSE][UTIM] utime(self, %s, %s)" % (path, str(times))
        subprocess.call(['adb', 'shell', 'touch', path])

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
