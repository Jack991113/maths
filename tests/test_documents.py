import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parents[1] / 'maths'
sys.path.insert(0, str(ROOT / 'scripts'))
from build_documents import validate, build_mistakes


def minimal_mistake():
    return {
        'title': '错题总结测试',
        'topic': '一元一次方程',
        'questions': [{'id': 1, 'stem': ['解方程 2x=6。'], 'solution': ['两边同除以 2，得 x=3。']}],
        'mistake_records': [{'question_id': 1, 'record_id': 'TEST-001', 'topic': '一元一次方程',
                             'evidence': '隔离测试记录，不属于学生档案。'}]
    }


class DocumentBehaviorTests(unittest.TestCase):
    def test_unknown_points_do_not_create_fictitious_marks(self):
        for value in ('omitted', None):
            with self.subTest(points=value), tempfile.TemporaryDirectory() as tmp:
                spec = minimal_mistake()
                if value is None:
                    spec['questions'][0]['points'] = None
                    spec['questions'][0]['scoring'] = None
                    spec['total_points'] = None
                questions = validate(spec, 'mistakes')
                output = build_mistakes(spec, Path(tmp), {}, questions)
                text = '\n'.join(p.text for p in Document(output).paragraphs)
                self.assertIn('解方程 2x=6', text)
                self.assertIn('x=3', text)
                self.assertNotIn(' 分）', text)
                self.assertNotIn('满分', text)

    def test_string_stem_is_rejected_instead_of_split_into_characters(self):
        spec = minimal_mistake()
        spec['questions'][0]['stem'] = '解方程 2x=6。'
        with self.assertRaisesRegex(ValueError, 'paragraph array'):
            validate(spec, 'mistakes')

    def test_string_solution_is_rejected(self):
        spec = minimal_mistake()
        spec['questions'][0]['solution'] = 'x=3'
        with self.assertRaisesRegex(ValueError, 'paragraph array'):
            validate(spec, 'mistakes')

    def test_paper_score_mismatch_is_rejected(self):
        spec = json.loads((ROOT / 'assets/example-paper.json').read_text(encoding='utf-8'))
        spec['total_points'] = 141
        with self.assertRaisesRegex(ValueError, 'total_points'):
            validate(spec)

    def test_score_step_mismatch_is_rejected(self):
        spec = json.loads((ROOT / 'assets/example-paper.json').read_text(encoding='utf-8'))
        spec['sections'][2]['questions'][0]['scoring'][0]['points'] += 1
        with self.assertRaisesRegex(ValueError, 'scoring'):
            validate(spec)

    def test_reexport_does_not_overwrite_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            inp = base / 'input.json'
            inp.write_text(json.dumps(minimal_mistake(), ensure_ascii=False), encoding='utf-8')
            out = base / 'existing'
            out.mkdir()
            sentinel = out / 'keep.txt'
            sentinel.write_text('historical result', encoding='utf-8')
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/build_documents.py'),
                                   '--input', str(inp), '--out-dir', str(out), '--mode', 'mistakes'],
                                  text=True, capture_output=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('Output directory is not empty', proc.stderr)
            self.assertEqual(sentinel.read_text(), 'historical result')
            self.assertEqual([p.name for p in out.iterdir()], ['keep.txt'])


if __name__ == '__main__':
    unittest.main()
