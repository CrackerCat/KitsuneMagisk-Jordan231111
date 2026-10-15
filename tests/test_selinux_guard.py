from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
import subprocess,tempfile

def function(path,signature):
 s=(ROOT / path).read_text();start=s.index(signature);end=s.index('{',start);depth=1;i=end+1
 while depth:
  if s[i]=='{':depth+=1
  elif s[i]=='}':depth-=1
  i+=1
 return s[start:i]
s=function('native/src/core/selinux.rs','pub(crate) fn selinux_disabled()')
s=s.replace('std::fs::metadata(path)','std::fs::metadata(root.join(path.trim_start_matches(\'/\')))').replace('std::fs::read_to_string("/proc/self/attr/current")','std::fs::read_to_string(root.join("proc/self/attr/current"))').replace('std::fs::read_to_string("/sys/kernel/security/lsm")', 'std::fs::read_to_string(root.join("sys/kernel/security/lsm"))').replace('selinux_disabled()', 'selinux_disabled(root: &std::path::Path)')
prefix='mod libc { pub const ENOENT:i32=2; pub const EINVAL:i32=22; pub const ENODEV:i32=19; }\n'
main=r'''
fn main() {
 let root=std::path::PathBuf::from(std::env::args().nth(1).expect("root"));
 std::fs::create_dir_all(root.join("sys/fs/selinux")).expect("directory");
 std::fs::create_dir_all(root.join("proc/self/attr")).expect("directory");
 assert!(selinux_disabled(&root));
 for mode in ["0", "1", "garbage"] {
  std::fs::write(root.join("sys/fs/selinux/enforce"),mode).expect("mode");
  assert!(!selinux_disabled(&root));
 }
 std::fs::remove_file(root.join("sys/fs/selinux/enforce")).expect("remove");
 std::fs::write(root.join("proc/self/attr/current"),"u:r:zygote:s0\0").expect("context");
 assert!(!selinux_disabled(&root));
 std::fs::create_dir_all(root.join("sys/kernel/security")).expect("lsm directory");
 std::fs::write(root.join("proc/self/attr/current"),"unconfined").expect("AppArmor");
 std::fs::write(root.join("sys/kernel/security/lsm"),"capability,apparmor\n").expect("lsms");
 assert!(selinux_disabled(&root));
 for active in ["capability,selinux", "", "bad list", "selinux,apparmor"] {
  std::fs::write(root.join("sys/kernel/security/lsm"),active).expect("lsms");
  assert!(!selinux_disabled(&root));
 }
 std::fs::remove_file(root.join("sys/kernel/security/lsm")).expect("remove lsms");
 std::fs::write(root.join("proc/self/attr/current"),"").expect("empty");
 assert!(selinux_disabled(&root));
 std::fs::remove_file(root.join("proc/self/attr/current")).expect("remove");
 std::fs::create_dir(root.join("proc/self/attr/current")).expect("directory error");
 assert!(!selinux_disabled(&root));
 println!("SELinux absence/active/permissive/malformed/I/O-error guards passed");
}
'''
class SelinuxGuardTest(unittest.TestCase):
    def test_disabled_requires_positive_absence(self):
        with tempfile.TemporaryDirectory(prefix='kitsune-pr12-selinux-') as temp:
         p=Path(temp);source=p/'test.rs';source.write_text(prefix+s+main)
         subprocess.run(['rustc','--edition=2024',str(source),'-o',str(p/'test')],check=True)
         subprocess.run([str(p/'test'),str(p/'fs')],check=True)
