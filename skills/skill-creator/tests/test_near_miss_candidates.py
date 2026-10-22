from pathlib import Path
import sys
import pytest
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.skill_ir import Skill
from scripts.generate_tests import generate_near_miss_candidates, write_near_miss_candidates, promote_near_miss_candidates, generate_tests
from scripts.tests_loader import load_trigger_suite, TestCaseError


def skill_at(path, name='target', description='Create widgets.'):
    path.mkdir(parents=True)
    (path/'SKILL.md').write_text('---\n'+yaml.safe_dump({'name':name,'description':description})+'---\nBody\n', encoding='utf-8')
    return Skill.from_path(path)


def review(path, cases=None):
    path.write_text(yaml.safe_dump(cases if cases is not None else [{'prompt':'neighbor','reviewed':True,'should_trigger':False}]),encoding='utf-8')
    return path


def test_candidates(tmp_path):
    skill=skill_at(tmp_path/'target')
    skill_at(tmp_path/'neighbor','neighbor','Analyze widgets.')
    cases=generate_near_miss_candidates(skill,tmp_path)
    assert cases==generate_near_miss_candidates(skill,tmp_path)
    assert len(cases)==1 and cases[0]['adjacent_skill']=='neighbor'
    assert 'should_trigger' not in cases[0]
    output=write_near_miss_candidates(skill,tmp_path)
    original=output.read_bytes()
    assert load_trigger_suite(skill.skill_path/'tests')==[]
    with pytest.raises(ValueError,match='already exists'):
        write_near_miss_candidates(skill,tmp_path)
    write_near_miss_candidates(skill,tmp_path,replace=True)
    assert output.read_bytes()==original


@pytest.mark.parametrize('label',[None,'false',0])
def test_requires_boolean_and_review(tmp_path,label):
    skill=skill_at(tmp_path/'target')
    file=review(tmp_path/'review.yaml',[{'prompt':'x','reviewed':True,'should_trigger':label}])
    with pytest.raises(TestCaseError,match='boolean'):
        promote_near_miss_candidates(skill,file)
    review(file,[{'prompt':'x','reviewed':False,'should_trigger':False}])
    with pytest.raises(TestCaseError,match='reviewed'):
        promote_near_miss_candidates(skill,file)
    assert not (skill.skill_path/'tests').exists()


def test_dedupe_and_preservation(tmp_path):
    skill=skill_at(tmp_path/'target')
    tests=skill.skill_path/'tests'
    tests.mkdir()
    manual=tests/'should_trigger.yaml'
    manual.write_text('- prompt: existing\n  expected: true\n')
    original=manual.read_bytes()
    cases=[{'prompt':q,'reviewed':True,'should_trigger':v} for q,v in [('existing',True),('neighbor',False),(' neighbor ',False),('positive',True)]]
    file=review(tmp_path/'review.yaml',cases)
    output=promote_near_miss_candidates(skill,file)
    assert yaml.safe_load(output.read_text())==[{'query':'neighbor','should_trigger':False},{'query':'positive','should_trigger':True}]
    assert len(load_trigger_suite(tests))==3
    assert manual.read_bytes()==original
    with pytest.raises(TestCaseError,match='No new cases'):
        promote_near_miss_candidates(skill,file)


@pytest.mark.parametrize('replace', [False, True])
@pytest.mark.parametrize('existing_output', [False, True])
def test_empty_promotion_preserves_output(tmp_path, replace, existing_output):
    skill = skill_at(tmp_path / 'target')
    tests = skill.skill_path / 'tests'
    tests.mkdir()
    (tests / 'should_not_trigger.yaml').write_text('- prompt: neighbor\n  expected: false\n', encoding='utf-8')
    output = tests / 'generated' / 'near_misses.yaml'
    if existing_output:
        output.parent.mkdir()
        output.write_text('- query: previous\n  should_trigger: false\n', encoding='utf-8')
    before = output.read_bytes() if existing_output else None
    file = review(tmp_path / 'review.yaml', [{'prompt': ' neighbor ', 'reviewed': True, 'should_trigger': False}])

    with pytest.raises(TestCaseError, match='No new cases'):
        promote_near_miss_candidates(skill, file, replace=replace)

    assert (output.read_bytes() if output.exists() else None) == before
    assert output.parent.exists() == existing_output


def test_cli_empty_promotion_fails(tmp_path, monkeypatch, capsys):
    from scripts.generate_tests import _main
    skill = skill_at(tmp_path / 'target')
    file = review(tmp_path / 'review.yaml')
    output = promote_near_miss_candidates(skill, file)
    before = output.read_bytes()
    (skill.skill_path / 'tests' / 'should_not_trigger.yaml').write_text('- prompt: neighbor\n  expected: false\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['generate_tests', str(skill.skill_path), '--promote-candidates', str(file), '--replace'])

    assert _main() == 1
    captured = capsys.readouterr()
    assert 'No new cases' in captured.err
    assert 'Written to:' not in captured.out
    assert output.read_bytes() == before


def test_conflict_and_replace(tmp_path):
    skill=skill_at(tmp_path/'target')
    file=review(tmp_path/'review.yaml')
    output=promote_near_miss_candidates(skill,file)
    before=output.read_bytes()
    review(file,[{'prompt':'neighbor','reviewed':True,'should_trigger':True}])
    with pytest.raises(TestCaseError,match='conflicting'):
        promote_near_miss_candidates(skill,file)
    assert output.read_bytes()==before
    promote_near_miss_candidates(skill,file,replace=True)
    assert yaml.safe_load(output.read_text())[0]['should_trigger'] is True
    (skill.skill_path/'tests'/'should_not_trigger.yaml').write_text('- prompt: neighbor\n  expected: false\n')
    before=output.read_bytes()
    with pytest.raises(TestCaseError,match='conflicting'):
        promote_near_miss_candidates(skill,file,replace=True)
    assert output.read_bytes()==before


def test_bad_inputs_and_default(tmp_path):
    skill=skill_at(tmp_path/'target')
    with pytest.raises(ValueError,match='No eligible'):
        generate_near_miss_candidates(skill,tmp_path)
    skill_at(tmp_path/'bad','bad','')
    with pytest.raises(ValueError,match='name and description'):
        generate_near_miss_candidates(skill,tmp_path)
    with pytest.raises(ValueError,match='does not exist'):
        generate_near_miss_candidates(skill,tmp_path/'missing')
    file=tmp_path/'bad.yaml'
    file.write_text('[')
    with pytest.raises(yaml.YAMLError):
        promote_near_miss_candidates(skill,file)
    assert not (skill.skill_path/'tests').exists()
    assert len(generate_tests(skill))==6


def test_cli_modes(tmp_path, monkeypatch, capsys):
    from scripts.generate_tests import _main
    skill=skill_at(tmp_path/'target')
    skill_at(tmp_path/'neighbor','neighbor','Analyze widgets.')
    monkeypatch.setattr(sys,'argv',['generate_tests',str(skill.skill_path),'--adjacent-skills',str(tmp_path)])
    assert _main()==0
    assert 'Written to:' in capsys.readouterr().out
    assert _main()==1
    assert '--replace' in capsys.readouterr().err
    file=review(tmp_path/'review.yaml')
    monkeypatch.setattr(sys,'argv',['generate_tests',str(skill.skill_path),'--promote-candidates',str(file)])
    assert _main()==0
    monkeypatch.setattr(sys,'argv',['generate_tests',str(skill.skill_path),'--replace'])
    with pytest.raises(SystemExit) as exc:
        _main()
    assert exc.value.code==2
    monkeypatch.setattr(sys,'argv',['generate_tests',str(skill.skill_path),'--adjacent-skills',str(tmp_path),'--promote-candidates',str(file)])
    with pytest.raises(SystemExit) as exc:
        _main()
    assert exc.value.code==2
