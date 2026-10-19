#include "nvmtl_desktop_journal.h"
#include <pwd.h>
#include <stdlib.h>
static int flush_file(const char *path){int fd=open(path,O_WRONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return errno;struct stat st;int r=fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_nlink!=1?EINVAL:0;if(!r&&nvmtl_journal_flush(fd))r=errno;close(fd);return r;}
int main(int argc,char **argv){
#ifndef LATITUDE_JOURNAL_TEST
 if(geteuid()!=0){fputs("Run journal helper as root\n",stderr);return 2;}
#endif
 const char *path=NVMTL_DESKTOP_JOURNAL_PATH;
 if(argc<2)return 2;
 if(!strcmp(argv[1],"prepare")){
  char previous[1024];snprintf(previous,sizeof previous,"%s.previous",path);
  struct stat st;if(lstat(path,&st)==0){if(!S_ISREG(st.st_mode)||st.st_nlink!=1)return 2;if(rename(path,previous))return 2;}else if(errno!=ENOENT)return 2;
  int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return 2;
#ifndef LATITUDE_JOURNAL_TEST
  struct passwd *pw=getpwnam("_windowserver");if(!pw||fchown(fd,pw->pw_uid,pw->pw_gid)){close(fd);return 2;}
#endif
  if(nvmtl_journal_flush(fd)){close(fd);return 2;}close(fd);
  return nvmtl_journal_append(path,"prepared","candidate0.3.4",0)?2:0;
 }
 if(!strcmp(argv[1],"stage"))return nvmtl_journal_append(path,argc>2?argv[2]:"stage",argc>3?argv[3]:"",argc>4?atoi(argv[4]):0)?2:0;
 if(!strcmp(argv[1],"flush")&&argc==3)return flush_file(argv[2])?2:0;
 if(!strcmp(argv[1],"watch")){
  unsigned seconds=argc>2?(unsigned)strtoul(argv[2],NULL,10):120;if(seconds>120)return 2;
  const char *files[]={"/Library/Logs/LatitudeDesktopLive.log","/Library/Logs/LatitudeDesktopRegistry.log","/Library/Logs/LatitudePanelLoad.log"};
  for(unsigned t=0;t<seconds;t+=2){nvmtl_journal_append(path,"loader-heartbeat","capture watcher",(int)t);for(unsigned i=0;i<3;i++)flush_file(files[i]);sleep(2);}return 0;
 }
 return 2;
}
