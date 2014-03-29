#!/usr/bin/env python

import sys, time, bigsuds
from base64 import b64decode,b64decode

############################################################################
# file_download - Download file from F5
# Usage - file_download(bigip_obj,src_file,dst_file,chunk_size,buff = n)
#		bigip_obj - the bigsuds icontol object
#		src_file - file on F5
#		dst_file - local file
#		chunk_size - download size for each chunk
#		buff - (optional) size of file write buffer, default 1MB
# Returns - list  
# Element 0 - Job completed - True/False
# Element 1 - dict keys - 
#			  bytes - returns file size in bytes if job completed
#			  error - returns error message if job failed
############################################################################
def file_download(bigip_obj,src_file,dst_file,chunk_size,buff = 1048576):
	# Set begining vars
	download = 1
	foffset = 0
	timeout_error = 0 
	fbytes = 0
	
	# Open file for writing, default buffer size is 1MB
	try:
		f_dst = open(dst_file,'w',buff)
	except:
		e = sys.exc_info()[1]
		raise bigsuds.ConnectionError('Can\'t create file: %s' % e)
	
	# Main loop
	while download:
		# Try to download chunk
		try:
			chunk = bigip_obj.System.ConfigSync.download_file(file_name = src_file, chunk_size = chunk_size, file_offset = foffset)
		except:
			e = sys.exc_info()[1]
			timeout_error += 1
			if (timeout_error >= 3):
				raise bigsuds.ConnectionError(e)
			else:
				#  Wait 2 seconds before retry
				time.sleep(2)
				continue
		# reset error counter
		timeout_error = 0
		
		# Write contents to file
		fchunk = b64decode(chunk['return']['file_data'])
		f_dst.write(fchunk)
		fbytes += sys.getsizeof(fchunk) - 40
		
		# Check to see if chunk is end of file
		fprogress = chunk['return']['chain_type']
		if (fprogress == 'FILE_FIRST_AND_LAST')  or (fprogress == 'FILE_LAST' ):
			f_dst.close()
			download = 0
			return fbytes
		
		# set new file offset
		foffset = chunk['file_offset']

############################################################################
# active_image - Return a list of the active image
# Usage - active_image(obj)
#		  obj - The bigsuds connection object
# Returns - dict
#     {'version': 'str', 'build': 'str', 'partition': 'str'}
############################################################################
def active_image(obj):
	software = obj.System.SoftwareManagement.get_all_software_status()
	for i in software:
		if i['active'] == True:
			return {'version' : i['version'], 'build' : i['build'], 'partition' : i['installation_id']['install_volume']}

############################################################################
# device_info - returns useful info about F5 device
# Usage - device_info(obj)
#		  obj - The bigsuds connection object 
# Returns - dict
#		  {'model': 'str', 'hostname': 'str', 'type': 'str', 'serial': 'str'}
############################################################################
def device_info(obj):
	device = obj.System.SystemInfo.get_system_information()
	return {'hostname' : device['host_name'],'model' : device['platform'], 'type' : device['product_category'], 'serial' : device['chassis_serial']}
