#!/usr/bin/env python

############################ LICENSE #################################################
## Config Backup for F5 program to manage daily backups of F5 BigIP devices
## Copyright (C) 2014 Eric Flores
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#####################################################################################

import os, sys, time
import sqlite3 as sq
import bigsuds
import logging as log

# Add fbackup lib folder to sys.path 
sys.path.append('%s/lib' % sys.path[0])
# Import F5 backup libs
import ecommon
import m2secret
from econtrol import *

# Define global vars
error = None
dev_errors = None
db = None 
dbc = None 
date = None


############################################
# Error function
############################################
def add_error(jobid, device = ''):
	#Inc error counter
	global error,dev_errors
	error += 1
	
	#If device error add to list
	if len(device):
		dev_errors.append(device)
	
	# Insert error status into DB
	try:
		dbc.execute('''UPDATE JOBS SET ERRORS = $ERROR, DEVICE_W_ERRORS = ? 
							WHERE ID = ?''', (error,' '.join(dev_errors),jobid) )
		db.commit()
	except:
		e = sys.exc_info()[1]
		log.error('Can\'t update DB: add_error - %s' % e)




def getcreds(key):
	'''
getcreds(key) - Gets user credentials from DB 
args - key: encryption key used by m2secret 
Return - dict of creds
	'''
	# Get user and encypted pass from DB, convert to dict of str types
	dbc.execute("SELECT NAME,PASS FROM BACKUP_USER")
	raw_creds = dict(zip( ['name','passwd'], [str(i) for i in dbc.fetchone()] ))
	
	# Decrypt pass and return dict of creds
	secret = m2secret.Secret()
	secret.deserialize(raw_creds['passwd'])
	return { 'name' : raw_creds['name'], 'passwd' : secret.decrypt(key) }

def jobid():
	'''
jobid() - Create or clear job ID in DB
Returns - int of job ID
	'''
	# Check for job on same date
	dbc.execute("SELECT ID FROM JOBS WHERE DATE = ?", (date,))
	row = dbc.fetchone()
	
	try:
		if row:
			# Overwrite job info if same date
			dbc.execute('''UPDATE JOBS SET TIME = ?, COMPLETE = 0, 
				ERRORS = 0, DEVICE_TOTAL = 0,	DEVICE_COMPLETE = 0, 
				DEVICE_W_ERRORS = '0' WHERE ID = ?''',(int(time.time()),row[0]) )
			db.commit()
			jobid = row[0]
		else:
			# Create new job info
			dbc.execute('''INSERT INTO JOBS ('DATE','TIME','ERRORS','COMPLETE',
								'DEVICE_TOTAL','DEVICE_COMPLETE','DEVICE_W_ERRORS') 
								VALUES (?,?,0,0,0,0,0)''', (date,int(time.time())) )
			db.commit()
			# Get new job ID
			jobid = dbc.lastrowid
	except:
		e = sys.exc_info()[1]
		log.error('Can\'t update DB: job id - %s' % e )
		exit()
	return jobid


def dev_info(obj,dev_id):
	'''
dev_info(bigsuds_obj,dev_id) - gets bigip info 
 from device and inserts into DB
	'''
	dinfo = device_info(obj)
	dinfo.update(active_image(obj))
	dbc.execute('''UPDATE DEVICES SET VERSION = ?,
				BUILD = ?,
				MODEL = ?,
				HOSTNAME = ?,
				DEV_TYPE = ?,
				SERIAL = ?,
				ACT_PARTITION = ? 
				WHERE ID = ?''', 
				(dinfo['version'],
				dinfo['build'],
				dinfo['model'],
				dinfo['hostname'],
				dinfo['type'],
				dinfo['serial'],
				dinfo['partition'],
				dev_id)
			)
	db.commit() 

def get_certs(obj,dev_id):
	'''
get_certs(bigsuds_obj,dev_id) - gets cert info 
  from device and inserts into DB	
	'''
	ha_pair = obj.System.Failover.is_redundant()
	standby = obj.System.Failover.get_failover_state()
	# Is device stand alone or active device?
	if not ha_pair or standby == 'FAILOVER_STATE_ACTIVE':
		log.info('Device is standalone or active unit. Downloading cert info.')
		
		# Get certs from device
		certs = obj.Management.KeyCertificate.get_certificate_list("MANAGEMENT_MODE_DEFAULT")
		
		#Create list of certs for DB
		certlist = []
		for i in certs:
			certlist.append(
				(dev_id,
				i['certificate']['cert_info']['id'], 
				i['certificate']['issuer']['organization_name'],
				i['certificate']['expiration_date'],
				i['certificate']['serial_number'],
				i['certificate']['bit_length'],
				i['certificate']['subject']['country_name'],
				i['certificate']['subject']['state_name'],
				i['certificate']['subject']['locality_name'],
				i['certificate']['subject']['organization_name'],
				i['certificate']['subject']['division_name'],
				i['certificate']['subject']['common_name'])
			)
		# Insert list into DB
		dbc.executemany( '''INSERT INTO CERTS ('DEVICE',
		'NAME','ISSUER','EXPIRE','SN','KEY','SUB_C',
		'SUB_S','SUB_L','SUB_O','SUB_OU','SUB_CN') 
		VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', certlist)
		db.commit()
	else:
		log.info('Device is not standalone or active unit. Skipping cert info download.')

def clean_archive(num):
	'''
clean_archive() - Deletes old UCS files as
  set by UCS_ARCHIVE_SIZE setting	
	'''
	dev_folders = os.listdir(sys.path[0] + '/devices')
	for folder in dev_folders:
		# Get list of file from dir, match only ucs files, reverse sort
		ucslist = os.listdir('%s/devices/%s' % (sys.path[0], folder))
		ucslist = [i  for i in ucslist if '-backup.ucs' in i]
		ucslist.sort(reverse=True)
		# loop thought list from index of archive size onward
		for ucs in ucslist[ num: ]:
			# Delete files
			ucsfile = '%s/%s' % (folder,ucs)
			log.info('Deleting file: %s' % ucsfile)
			os.remove('%s/devices/%s' % (sys.path[0], ucsfile))

def ucs_db(device_dict):
	'''
ucs_db(device_dict) - Put ucs file names into DB	
	'''
	# Clear DB entries
	dbc.execute("DELETE FROM ARCHIVE")
	db.commit()
	
	file_list = []
	for dev in device_dict:
		# Get list of file from dir, match only ucs files, sort
		ucslist = os.listdir('%s/devices/%s' % (sys.path[0],dev['name']))
		ucslist = [i  for i in ucslist if '-backup.ucs' in i]
		ucslist.sort()
		
		# add files to list
		file_list += ([ (dev['id'],'%s/devices/%s/' % (sys.path[0],
							dev['name']),ucs) for ucs in ucslist])
	
	# insert file info into DB
	dbc.executemany("INSERT INTO ARCHIVE ('DEVICE','DIR','FILE') VALUES (?,?,?);", file_list)
	db.commit()

def clean_logs(num):
	'''
clean_logs() - Deletes old log files as
  set by LOG_ARCHIVE_SIZE setting
	'''
	# Get list of files, match only log files, reverse sort
	logs = os.listdir('%s/log/' % sys.path[0])
	logs = [i  for i in logs if '-backup.log' in i]
	logs.sort(reverse=True)
	for lfile in logs[ num: ]:
		log.info('Deleting log file: %s' % lfile)
		os.remove('%s/log/%s' % (sys.path[0],lfile))

def clean_jobdb(num):
	'''
clean_logdb() - Deletes old job info from
  BD as set by LOG_ARCHIVE_SIZE setting 
	'''
	dbc.execute('SELECT ID FROM JOBS')
	jobs = [ idn[0] for idn in dbc.fetchall() ]
	jobs.sort(reverse=True)
	deljobs = jobs[ num: ]
	dbc.executemany('DELETE FROM JOBS WHERE ID = ?', str(deljobs) )
	db.commit()

#*************************************************************************
# MAIN 
#*************************************************************************
def main():
	# Global vars
	global error, dev_errors, db, dbc, date
	
	# set global vars
	date = time.strftime("%Y-%m-%d",time.localtime()) 
	error = 0 
	dev_errors = [] 
	
	# Local vars
	dev_complete = 0
	
	# Open/overwrite new log file. Quit if permission denied.
	try:
		log.basicConfig(filename='%s/log/%s-backup.log' % (sys.path[0], date),
			level=log.INFO,
			format='%(asctime)s %(levelname)s: %(message)s',
			datefmt='%Y-%m-%d %H:%M:%S'
		)
	except:
		e = sys.exc_info()[1]
		print 'Error:', e,'Can\'t write to log file. Exiting program!'
		exit()
	
	log.info('--------- Starting backup job.----------')
	 
	# Connect to DB
	log.info('Opening database file.')
	try:
		db = sq.connect(sys.path[0] + '/db/main.db')
	except:
		e = sys.exc_info()[1]
		log.critical('Can\'t open data base - %s.Exiting program!' % e)
		exit()
	
	dbc = db.cursor()
	
	# Log job in DB
	job_id = jobid()
	
	# Get credentials from DB
	log.info('Retrieving credentials from DB.')
	try:
		with open(sys.path[0] + '/.keystore/backup.key','r') as psfile:
			cryptokey =  psfile.readline().rstrip()
		creds = getcreds(cryptokey)
	except:
		e = sys.exc_info()[1]
		log.critical('Can\'t get credentials from DB - %s. Exiting program!' % e)
		add_error(job_id)
		exit()
	
	# Get backup settings from DB
	dbc.execute("SELECT NAME,VALUE FROM BACKUP_SETTINGS_INT")
	backup_config = dict(dbc.fetchall())
	
	# Get list of devices
	dbc.execute("SELECT ID,NAME,IP,CID_TIME FROM DEVICES")
	devices = [ {'id' : idn, 'name' : name, 'ip' : ip, 'cid': cid} for idn, name, ip, cid in dbc.fetchall() ]
	
	# Delete all certs from DB
	try:
		dbc.execute('DELETE FROM CERTS')
		db.commit()
	except:
		e = sys.exc_info()[1]
		log.error('Can\'t update DB: clear certs - %s' % e )	
		add_error(job_id)
	
	# Write number of devices to log DB
	num_devices = len(devices)
	log.info('There are %d devices to backup.' % num_devices)
	try:
		dbc.execute('UPDATE JOBS SET DEVICE_TOTAL = ? WHERE ID = ?',(num_devices,job_id))
		db.commit()
	except:
		e = sys.exc_info()[1]
		log.error('Can\'t update DB: num_devices - %s' % e )	
		add_error(job_id)
		exit()
	del num_devices
	
	# Loop through devices
	for dev in devices:
		log.info('Connecting to %s.' % dev['name'])
		# Create device folder if it does not exist
		try:
			os.mkdir('%s/devices/%s' % (sys.path[0],dev['name']),0775)
		except OSError, e:
			# If error is not from existing file errno 17
			if e.errno != 17: 
				log.error('Cannot create device archive folder - %s. Skipping to next device' % e )
				add_error(job_id,str(dev['id']))
				continue
		else:
			log.info('Created device directory %s/devices/%s' % (sys.path[0],dev['name']))
		
		# Get IP for device or keep hostname if NULL
		ip = dev['name'] if dev['ip'] == 'NULL' else dev['ip']
		
		# create connection object
		b = bigsuds.BIGIP(hostname = ip, username = creds['name'], password = creds['passwd']) 
		
		# Get device info
		try:
			dev_info(b,dev['id'])
		except:
			e = sys.exc_info()[1]
			log.error('%s' % e)
			add_error(job_id,str(dev['id']) )
			continue
		
		# Get CID from device
		try:
			cid = int(b.Management.DBVariable.query(['Configsync.LocalConfigTime'])[0]['value'])
		except:
			e = sys.exc_info()[1]
			log.error('%s' % e)
			add_error(job_id,str(dev['id']) )
			continue
		
		# Compare old cid time to new cid time
		if cid == dev['cid']:
			log.info('CID times match for %s. Configuration unchanged. Skipping download.' % dev['name'])
		else:
			log.info('CID times do not match. Old - %d, New - %d. Downloading backup file.' % (dev['cid'],cid)) 
			# Make device create UCS file, Download UCS file, Disconnect session, Write new cid time to DB
			try:
				b.System.ConfigSync.save_configuration(filename = 'configbackup.ucs',save_flag = 'SAVE_FULL')
				dbytes = file_download(
					b,'/var/local/ucs/configbackup.ucs',
					'%s/devices/%s/%s-%s-backup.ucs' % (sys.path[0], 
					dev['name'],date,dev['name']) ,65535
				)
				log.info('Downloaded UCS file for %s - %d bytes.' % (dev['name'],dbytes))
				db.execute('''UPDATE DEVICES SET CID_TIME = ?, 
							LAST_DATE = ? WHERE ID = ?''', (cid,int(time.time()),dev['id']))
				db.commit()
			except:
				e = sys.exc_info()[1]
				log.error('%s' % e)
				add_error(job_id,str(dev['id']) )
				continue
		
		# Get cert info 
		try:
			get_certs(b,dev['id'])
		except:
			e = sys.exc_info()[1]
			log.error('%s' % e )
			add_error(job_id,str(dev['id']))
			continue
		
		# Update DB with new complete count
		dev_complete += 1
		try:
			dbc.execute('UPDATE JOBS SET DEVICE_COMPLETE = ? WHERE ID = ?', (dev_complete,job_id) )
			db.commit()
		except:
			e = sys.exc_info()[1]
			log.error('Can\'t update DB: dev_complete - %s' % e )
			add_error(job_id,str(dev['id']))
	
	# Clear creds & key
	creds = None
	cryptokey = None
	
	#  Add deletion note to log file
	log.info('Starting DB, log, UCS file cleanup.')
	
	# Keep only the number of UCS files specified by UCS_ARCHIVE_SIZE and write deletion to log
	clean_archive(backup_config['UCS_ARCHIVE_SIZE'])
	
	# Insert files names into DB
	ucs_db(devices)
	
	# Keep only the number of log files specified by LOG_ARCHIVE_SIZE and write deletion to log
	clean_logs(backup_config['LOG_ARCHIVE_SIZE'])
	
	# Clean jobs logs from DB
	clean_jobdb(backup_config['LOG_ARCHIVE_SIZE'])
	
	log.info('Cleanup finished.')
	
	# Mark job as complete in DB
	db.execute('UPDATE JOBS SET COMPLETE = 1 WHERE ID = %d' % job_id)
	db.commit()
	
	# Close DB connection
	log.info('Closing DB connection.')
	db.close()
	
	# All done, close log file
	log.info('Backup job completed.')
	
	# Clear global vars
	error = None
	dev_errors = None
	db = None 
	dbc = None
	date = None