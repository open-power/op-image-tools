# IBM_PROLOG_BEGIN_TAG
# This is an automatically generated prolog.
#
# $Source: public/common/utils/imageProcs/tools/pymod/pakutils.py $
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
# Jason Albert - created 02/02/2022
# Python module to define common utility functions

############################################################
# Imports - Imports - Imports - Imports - Imports - Imports
############################################################
import datetime

############################################################
# Function - Functions - Functions - Functions - Functions
############################################################
def formatTime(timePassed, fraction=True):
    '''
    Handles time formatting in common function
    '''
    # The time comes out as 0:00:45.3482..
    # We find the break from the full seconds to the fractional seconds
    timeString = str(datetime.timedelta(seconds=timePassed))
    decIdx = timeString.find(".")

    if (fraction):
        # The second half of this is a bit of a mess
        # Convert the decimal string to a float, then round it to two places, then turn it back into a string
        # It has to be a formatted string conversion, a simple str() would turn .10 into .1.  Then remove the "0."
        return timeString[0:decIdx] + ("%.2f" % round(float(timeString[decIdx:]), 2))[1:]
    else:
        return timeString[0:decIdx]

# This is a modified version of code here
# https://stackoverflow.com/questions/12523586/python-format-size-application-converting-b-to-kb-mb-gb-tb
def humanBytes(B):
    '''
    Return the given bytes as a human friendly KB, MB, GB, or TB string
    '''
    B = int(B)
    KB = float(1024)
    MB = float(KB ** 2) # 1,048,576
    GB = float(KB ** 3) # 1,073,741,824
    TB = float(KB ** 4) # 1,099,511,627,776

    if B < KB:
        return '{0}B'.format(B)
    elif KB <= B < MB:
        return '{0:.2f}K'.format(B/KB)
    elif MB <= B < GB:
        return '{0:.2f}M'.format(B/MB)
    elif GB <= B < TB:
        return '{0:.2f}G'.format(B/GB)
    elif TB <= B:
        return '{0:.2f}T'.format(B/TB)
