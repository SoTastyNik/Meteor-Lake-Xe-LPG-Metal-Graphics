from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'latitude-desktop/tools/latitude-readback-test.m';s=f.read_text();s=s.replace('static atomic_int failed;', 'static atomic_int failed;\nstatic FILE *terminal;')
s=s.replace('if (!atomic_exchange(&failed,1)) fprintf(stderr,"FAIL worker=%u frame=%u: %s\\n",worker,frame,why);','''if (!atomic_exchange(&failed,1)) {
  fprintf(stderr,"FAIL worker=%u frame=%u: %s\\n",worker,frame,why);
  if(terminal)fprintf(terminal,"FAIL worker=%u frame=%u: %s\\n",worker,frame,why);
 }''')
s=s.replace('kr==KERN_SUCCESS?(unsigned long long)info.resident_size:0ull);','''kr==KERN_SUCCESS?(unsigned long long)info.resident_size:0ull);
   if(terminal)fprintf(terminal,"progress worker=%u frames=%u/%u resident=%llu\\n",worker,frame+1,iterations,kr==KERN_SUCCESS?(unsigned long long)info.resident_size:0ull);''')
s=s.replace('setbuf(stdout,NULL);','setbuf(stdout,NULL);\n if(!isatty(STDOUT_FILENO)) { terminal=fopen("/dev/tty","w");if(terminal)setbuf(terminal,NULL); }',1)
f.write_text(s)
# Clear inherited experimental switches so each comparison controls one factor.
f=r/'latitude-desktop/test-readback.sh';s=f.read_text().replace('-u VK_INSTANCE_LAYERS "${envargs[@]}"','-u VK_INSTANCE_LAYERS -u NVMTL_ASYNC_TEX_UPLOAD "${envargs[@]}"');f.write_text(s)
