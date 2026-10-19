# Copyright © 2017 Intel Corporation
# SPDX-License-Identifier: MIT

inc_intel = include_directories('.')
inc_intel_compiler = include_directories('compiler')

with_intel_elk = get_option('intel-elk')

intel_common_args = []
if with_intel_elk
  intel_common_args += ['-DINTEL_USE_ELK']
else
  if with_gallium_crocus or with_intel_hasvk
    error('Cannot build Crocus or Hasvk with meson option -Dintel-elk=false set.')
  endif
endif

subdir('mda')
subdir('genxml')
subdir('dev')
subdir('isl')
subdir('common')
subdir('compiler')
if with_intel_hasvk or with_intel_vk or with_gallium_crocus or with_gallium_iris
  subdir('blorp')
endif
subdir('decoder')
if with_intel_vk or with_gallium_iris
  subdir('shaders')
endif
if with_intel_hasvk or with_intel_vk or with_gallium_crocus or with_gallium_iris or with_intel_tools
  subdir('perf')
endif
if with_intel_hasvk or with_intel_vk or with_gallium_iris
  subdir('ds')
endif
subdir('metrics_library')
if with_intel_tools
  subdir('tools')
  subdir('executor')
endif
# The Intel tools need glibc; the noop drm-shim (a fake i915 kernel driver) does not.
if with_tools.contains('drm-shim') and not with_intel_tools
  libintel_stub_gpu = shared_library(
    'intel_noop_drm_shim',
    [files('tools/intel_noop_drm_shim.c'), intel_dev_serialize_src],
    include_directories: [inc_include, inc_src, inc_intel],
    dependencies: [dep_libdrm, dep_drm_shim, idep_mesautil, idep_libintel_common, idep_intel_dev, idep_parson],
    gnu_symbol_visibility : 'hidden',
    install : true,
  )
endif
if get_option('vulkan-layers').contains('intel-nullhw')
  subdir('nullhw-layer')
endif
if with_intel_vk
  subdir('vulkan')
endif
if with_intel_hasvk
  subdir('vulkan_hasvk')
endif
