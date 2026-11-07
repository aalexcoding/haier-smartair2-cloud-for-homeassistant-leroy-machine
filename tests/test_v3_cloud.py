"""Pure protocol tests, independent of HA and the vendor cloud."""
from pathlib import Path
import importlib.util


FILE = Path(__file__).resolve().parents[1] / 'custom_components' / 'haier_smartair2' / 'v3_cloud.py'
spec = importlib.util.spec_from_file_location('haier_v3_cloud_under_test', FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def attrs_for_device(*, mode='4', fan='5'):
    data = {key: f'value_{i}' for i, key in enumerate(module.V3_ARGUMENTS)}
    data.update(onOffStatus='true', operationMode=mode, windSpeed=fan,
                targetTemperature='24.00', windDirectionVertical='2',
                windDirectionHorizontal='0', healthMode='false',
                pm2p5CleaningStatus='false', ch2oCleaningStatus='false')
    return data


def test_v3_modes_are_documented_codes():
    assert module.V3_MODE_TO_CODE == {0:'0',1:'1',4:'2',2:'4',3:'6'}
    assert module.V3_FAN_TO_CODE == {0:'1',1:'2',2:'3',3:'5'}


def test_fan_only_and_low_fan_sequence():
    assert module.fan_change(2) == {'windSpeed':'3'}
    assert module.mode_change(3) == {'operationMode':'6'}


def test_all_32_args_and_preservation():
    attrs=attrs_for_device()
    args=module.make_grsetdac_args(attrs, {'operationMode':'6'})
    assert len(args)==32
    assert [next(iter(x)) for x in args] == list(module.V3_ARGUMENTS)
    value_map={k:v for arg in args for k,v in arg.items()}
    assert value_map['operationMode']=='6'
    assert value_map['windSpeed']=='5'
    assert value_map['windDirectionVertical']=='2'
    assert value_map['targetTemperature']=='24.00'


def test_no_cross_device_attrs():
    first=attrs_for_device(mode='4',fan='5')
    second=attrs_for_device(mode='1',fan='1')
    a=module.make_grsetdac_args(first, {'windDirectionVertical':'8'})
    b=module.make_grsetdac_args(second, {'healthMode':'true'})
    va={k:v for x in a for k,v in x.items()}
    vb={k:v for x in b for k,v in x.items()}
    assert va['operationMode']=='4' and va['windSpeed']=='5'
    assert vb['operationMode']=='1' and vb['windSpeed']=='1'
    assert vb['healthMode']=='true' and va['healthMode']=='false'


def test_missing_required_field_blocks_group_write():
    attrs=attrs_for_device()
    attrs.pop('specialMode')
    try:
        module.make_grsetdac_args(attrs, {'operationMode':'1'})
    except ValueError as exc:
        assert 'specialMode' in str(exc)
    else:
        assert False, 'Must not send incomplete group write'


def test_only_two_observed_default_fields_allowed():
    attrs=attrs_for_device()
    attrs.pop('cloudFilterChangeFlag')
    attrs.pop('cleaningTimeStatus')
    args=module.make_grsetdac_args(attrs, {'operationMode':'1'})
    val={k:v for x in args for k,v in x.items()}
    assert val['cloudFilterChangeFlag']=='false'
    assert val['cleaningTimeStatus']=='false'


def test_float_setpoint_ack_value():
    assert module.same_attr('targetTemperature','24.00','24')
    assert not module.same_attr('targetTemperature','24.00','25')


def test_purify_switch_controls_all_three_fields():
    assert module.extra_change('purify', True) == {
        'healthMode':'true','pm2p5CleaningStatus':'true','ch2oCleaningStatus':'true'}
    assert module.extra_change('purify', False) == {
        'healthMode':'false','pm2p5CleaningStatus':'false','ch2oCleaningStatus':'false'}


def test_independent_swings():
    assert module.extra_change('swing_vertical',True)=={'windDirectionVertical':'8'}
    assert module.extra_change('swing_vertical',False)=={'windDirectionVertical':'0'}
    assert module.extra_change('swing_horizontal',True)=={'windDirectionHorizontal':'7'}
    assert module.extra_change('swing_horizontal',False)=={'windDirectionHorizontal':'0'}


def test_attribute_value_comparison_is_case_insensitive_only_for_booleans():
    assert module.attrs_match({'onOffStatus':'True'},{'onOffStatus':'true'})
    assert not module.attrs_match({'onOffStatus':'false'},{'onOffStatus':'true'})
    assert not module.attrs_match({}, {'onOffStatus':'true'})


def test_no_hardcoded_device_restrictions_in_distributed_code():
    import re
    for file in (Path(__file__).resolve().parents[1]/'custom_components'/'haier_smartair2').glob('*.py'):
        text = file.read_text()
        assert not re.search(r'devid\s*(?:==|!=)\s*[\"\'][A-F0-9]{16}[\"\']', text)
        assert 'Office Alex' not in text
