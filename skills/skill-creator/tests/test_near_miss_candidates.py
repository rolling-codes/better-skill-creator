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
    with pytest.raises(TestCaseError,match='No new cases remain'):
        promote_near_miss_candidates(skill,file)


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


@pytest.mark.parametrize('replace', [False, True])
def test_duplicate_only_promotion_preserves_output(tmp_path, replace):
    skill = skill_at(tmp_path/'target')
    tests = skill.skill_path/'tests'
    tests.mkdir()
    (tests/'should_trigger.yaml').write_text('- prompt: existing\n  expected: true\n', encoding='utf-8')
    reviewed = review(tmp_path/'review.yaml', [{'prompt': ' existing ', 'reviewed': True, 'should_trigger': True}])
    output = tests/'generated'/'near_misses.yaml'
    before = b''
    if replace:
        output.parent.mkdir()
        output.write_text('- query: accepted earlier\n  should_trigger: false\n', encoding='utf-8')
        before = output.read_bytes()
    with pytest.raises(TestCaseError, match='No new cases remain'):
        promote_near_miss_candidates(skill, reviewed, replace=replace)
    if replace:
        assert output.read_bytes() == before
    else:
        assert not output.exists()


def test_cli_duplicate_only_promotion_reports_failure(tmp_path, monkeypatch, capsys):
    from scripts.generate_tests import _main
    skill = skill_at(tmp_path/'target')
    tests = skill.skill_path/'tests'
    tests.mkdir()
    (tests/'should_trigger.yaml').write_text('- prompt: existing\n  expected: true\n', encoding='utf-8')
    reviewed = review(tmp_path/'review.yaml', [{'prompt': 'existing', 'reviewed': True, 'should_trigger': True}])
    monkeypatch.setattr(sys, 'argv', ['generate_tests', str(skill.skill_path), '--promote-candidates', str(reviewed)])
    assert _main() == 1
    captured = capsys.readouterr()
    assert 'No new cases remain' in captured.err
    assert 'Written to:' not in captured.out
    assert not (tests/'generated'/'near_misses.yaml').exists()


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


@pytest.mark.parametrize('frontmatter,body,expected_name,expected_description', [
    ({'description': 'Analyze widgets.'}, 'Body', 'neighbor', 'Analyze widgets.'),
    ({'name': 'analyzer'}, '\nAnalyze widgets.\nExtra instructions.', 'analyzer', 'Analyze widgets.'),
    ({}, '\nAnalyze widgets.\nExtra instructions.', 'neighbor', 'Analyze widgets.'),
    ({'name': 'explicit', 'description': 'Explicit scope.'}, 'Body fallback.', 'explicit', 'Explicit scope.'),
    ({'description': 'Analyze widgets.', 'when_to_use': 'Use for inventory questions.'},
     'Body', 'neighbor', 'Analyze widgets. Use for inventory questions.'),
    ({'when_to_use': 'Use for inventory questions.'},
     'Analyze widgets.', 'neighbor', 'Analyze widgets. Use for inventory questions.'),
])
def test_claude_neighbor_metadata_defaults(tmp_path, frontmatter, body, expected_name, expected_description):
    skill = skill_at(tmp_path / 'target')
    neighbor = tmp_path / 'neighbor'
    neighbor.mkdir()
    source = '---\n' + yaml.safe_dump(frontmatter) + '---\n' + body + '\n'
    (neighbor / 'SKILL.md').write_text(source, encoding='utf-8')
    cases = generate_near_miss_candidates(skill, tmp_path)
    assert len(cases) == 1
    assert cases[0]['adjacent_skill'] == expected_name
    assert f'but my request is: {expected_description} Please help' in cases[0]['prompt']
    assert (neighbor / 'SKILL.md').read_text(encoding='utf-8') == source
    # Generator defaults do not change the IR's strict representation.
    parsed = Skill.from_path(neighbor)
    if 'name' not in frontmatter:
        assert parsed.name == ''
    if 'description' not in frontmatter:
        assert parsed.description == ''


@pytest.mark.parametrize('field', ['name', 'description', 'when_to_use'])
@pytest.mark.parametrize('value', [None, False, 42, ['text'], {'text': 'value'}])
def test_malformed_neighbor_metadata_is_actionable(tmp_path, field, value):
    skill = skill_at(tmp_path / 'target')
    neighbor = tmp_path / 'neighbor'
    neighbor.mkdir()
    frontmatter = {'name': 'neighbor', 'description': 'Analyze widgets.', field: value}
    (neighbor / 'SKILL.md').write_text(
        '---\n' + yaml.safe_dump(frontmatter) + '---\nBody fallback.\n', encoding='utf-8'
    )
    with pytest.raises(ValueError, match=f'{field} must be a string') as exc:
        generate_near_miss_candidates(skill, tmp_path)
    assert str(neighbor) in str(exc.value)
    assert not (skill.skill_path / 'tests').exists()


@pytest.mark.parametrize('frontmatter,body', [
    ({'name': '', 'description': 'Analyze widgets.'}, 'Body fallback.'),
    ({'name': 'neighbor', 'description': '  '}, 'Body fallback.'),
    ({'name': 'neighbor'}, '\n  \n'),
])
def test_empty_neighbor_metadata_has_no_implicit_fallback(tmp_path, frontmatter, body):
    skill = skill_at(tmp_path / 'target')
    neighbor = tmp_path / 'neighbor'
    neighbor.mkdir()
    (neighbor / 'SKILL.md').write_text(
        '---\n' + yaml.safe_dump(frontmatter) + '---\n' + body, encoding='utf-8'
    )
    with pytest.raises(ValueError, match='name and description'):
        generate_near_miss_candidates(skill, tmp_path)
