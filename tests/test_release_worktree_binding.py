"""Real disposable Git repositories: release inputs remain bound to their worktree."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('worktree_release',ROOT/'scripts/core_next/release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
LAB=r.canonical_lab(ROOT)

class WorktreeBindingTests(unittest.TestCase):
    def setUp(self):
        (LAB/'tests').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='release-lineage-')
        self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.clone=self.base/'application';self.clone.mkdir()
        self.git('init','--quiet')
        (self.clone/'identity.txt').write_text('canonical-source',encoding='utf-8')
        self.git('add','identity.txt');self.git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','fixture')
        self.work=self.base/'elsewhere'/'candidate';self.work.parent.mkdir()
        self.git('worktree','add','--quiet','--detach',str(self.work),'HEAD')
        self.expected=self.base/'application-LAB'
    def git(self,*args):
        return subprocess.check_output([r.GIT,'--no-optional-locks','-C',str(self.clone),*args],stderr=subprocess.DEVNULL).decode().strip()
    def test_canonical_and_linked_worktree_share_one_lab(self):
        self.assertEqual(r.canonical_lab(self.clone),self.expected)
        self.assertEqual(r.canonical_lab(self.work),self.expected)
        self.assertNotEqual(r.canonical_lab(self.work),self.work.parent/(self.work.name+'-LAB'))
    def test_source_lookup_keeps_different_worktree_head(self):
        (self.work/'identity.txt').write_text('candidate-source',encoding='utf-8')
        subprocess.check_call([r.GIT,'-C',str(self.work),'add','identity.txt'])
        subprocess.check_call([r.GIT,'-C',str(self.work),'-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','candidate'])
        self.assertEqual(r.canonical_lab(self.work),self.expected)
        self.assertNotEqual(self.git('rev-parse','HEAD'),subprocess.check_output([r.GIT,'-C',str(self.work),'rev-parse','HEAD']).decode().strip())
        self.assertEqual(subprocess.check_output([r.GIT,'-C',str(self.work),'show','HEAD:identity.txt']),b'candidate-source')
    def test_unregistered_copied_pointer_rejected(self):
        forged=self.base/'forged';forged.mkdir();(forged/'.git').write_bytes((self.work/'.git').read_bytes())
        with self.assertRaises(RuntimeError):r.canonical_lab(forged)
    def test_missing_git_or_nongit_root_rejected(self):
        with self.assertRaises(RuntimeError):r.canonical_lab(self.base)
        with self.assertRaises(RuntimeError):r.canonical_lab(self.work,git=str(self.base/'missing-git.exe'))
    def test_reparse_ancestor_rejected_before_resolution(self):
        real=Path.lstat
        def altered(p,*args,**kwargs):
            observed=real(p,*args,**kwargs)
            if p==self.work.parent:
                class Reparse:
                    st_mode=observed.st_mode
                    st_file_attributes=0x400
                return Reparse()
            return observed
        with patch.object(Path,'lstat',altered),self.assertRaises(RuntimeError):r.canonical_lab(self.work)
    def test_subdirectory_not_a_registered_release_root(self):
        sub=self.work/'sub';sub.mkdir()
        with self.assertRaises(RuntimeError):r.canonical_lab(sub)

if __name__=='__main__':unittest.main()
