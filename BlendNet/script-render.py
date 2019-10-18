#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Script Render

Description: Special script used by the agent to render the task
'''

# Since blender reports status only to stdout - we need this
# separated script to watch on progress from the agent process.
#
# When it will be possible to read the status of render directly
# from python - we will be able to use agent without the script:
# the main trick there - to call open file/render through queue
# from the main thread, because blender hate threading.

import signal # The other better ways are not working for subprocess...
signal.signal(signal.SIGTERM, lambda s, f: print('WARN: Dodged TERM subprocess'))

import os, sys, json
sys.path.append(os.path.dirname(__file__))

import disable_buffering
import blend_file

# Read current task specification from json file
task = None
with open(sys.argv[-1], 'r') as f:
    task = json.load(f)

import random # To generate seed for rendering
import threading # To run timer and flush render periodically

import bpy

print('INFO: Loading project file "%s"' % task['project'])
bpy.ops.wm.open_mainfile(filepath=task['project'])

scene = bpy.context.scene

# Set some required variables
print('INFO: Set scene vars')
scene.render.use_overwrite = True
scene.render.use_compositing = False # Don't use because Composite layer impossible to merge
scene.render.use_sequencer = False # No need for still images

# Switch to use maximum threads possible on the worker
scene.render.threads_mode = 'AUTO'

scene.cycles.device = 'CPU' # The only one supported right now

# Set sampling
print('INFO: Set sampling')
if scene.cycles.progressive == 'PATH':
    scene.cycles.samples = task['samples']
elif scene.cycles.progressive == 'BRANCHED_PATH':
    scene.cycles.aa_samples = task['samples']
else:
    print('ERROR: Unable to determine the sampling integrator')
    sys.exit(1)

# Set task seed or use random one (because we need an unique render pattern)
scene.cycles.seed = task.get('seed', random.randrange(0, 2147483647))

# Set frame if provided
if 'frame' in task:
    scene.frame_current = task['frame']

print('INFO: Disable denoising and use progressive refine')
# TODO: Enable the required channels to apply denoise after merge
bpy.context.view_layer.cycles['use_denoising'] = False
scene.cycles.use_progressive_refine = True

try:
    import _cycles
    _cycles.enable_print_stats() # Show detailed render statistics after the render
except:
    pass

print('INFO: Checking existance of the dependencies')
blend_file.getDependencies()

class Commands:
    def savePreview():
        scene.render.image_settings.file_format = 'OPEN_EXR'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '32'
        scene.render.image_settings.exr_codec = 'DWAA'
        bpy.data.images['Render Result'].save_render('_preview.exr')
        os.rename('_preview.exr', 'preview.exr')

    def saveRender():
        scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.color_depth = '32'
        scene.render.image_settings.exr_codec = 'ZIP'
        bpy.data.images['Render Result'].save_render('_render.exr')
        os.rename('_render.exr', 'render.exr')

def executeCommand(name):
    func = getattr(Commands, name, None)
    if callable(func):
        func()
        print('INFO: Command "%s" completed' % name)
    else:
        print('ERROR: Unable to execute "%s" command' % name)

def stdinProcess():
    '''Is used to get commands from the parent process'''
    for line in iter(sys.stdin.readline, b''):
        try:
            command = line.strip()
            if command == 'end':
                break
            executeCommand(command)
        except Exception as e:
            print('ERROR: Exception during processing stdin: %s' % e)

input_thread = threading.Thread(target=stdinProcess)
input_thread.start()
print('INFO: Starting render process')

# Start the render process
bpy.ops.render.render()

print('INFO: Render process completed')

# Render complete - saving the result image
executeCommand('saveRender')

print('INFO: Save render completed')
