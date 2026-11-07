"""Additional black-box tests derived from existing brief requirements."""
from copy import deepcopy


def step(action, test_id, value=''):
    return {'action': action, 'test_id': test_id, 'value': value}


def audit_case(case):
    case = deepcopy(case)
    kind = case['spec']['interactions'][0]['id']
    # A disabled decrement at the minimum is valid. Still assert the resulting value;
    # a control incorrectly disabled above the minimum continues to fail the assertion.
    if kind == 'stepper':
        for test in case['tests']:
            for instruction in test['steps']:
                if instruction['action'] == 'click' and instruction['test_id'] == 'quantity-minus':
                    instruction['action'] = 'click_if_enabled'
    s = step
    extra = {
        'filter': [s('fill', 'search', 'aTlAs'), s('expect_visible', 'item-atlas'), s('expect_hidden', 'item-beacon'),
                   s('fill', 'search', 'no-matching-entry-923'), s('expect_hidden', 'item-atlas'), s('expect_hidden', 'item-beacon'),
                   s('fill', 'search', ''), s('expect_visible', 'item-atlas'), s('expect_visible', 'item-beacon')],
        'toggle': [s('press', 'task-toggle', 'Space'), s('expect_text', 'task-status', 'Completed'),
                   s('press', 'task-toggle', 'Space'), s('expect_text', 'task-status', 'Pending')],
        'form': [s('fill', 'name', 'Alex Example'), s('click', 'submit'), s('expect_text', 'form-status', 'Required'),
                 s('fill', 'email', 'alex@example.com'), s('click', 'submit'), s('expect_text', 'form-status', 'Confirmed')],
        'tabs': [s('press', 'tab-details', 'Enter'), s('expect_text', 'tab-panel', 'Breakdown'),
                 s('press', 'tab-overview', 'Enter'), s('expect_text', 'tab-panel', 'Summary')],
        'cart': [s('click_if_enabled', 'remove-item'), s('expect_text', 'cart-count', '0'),
                 s('click', 'add-item'), s('click', 'add-item'), s('expect_text', 'cart-count', '2'),
                 s('click', 'remove-item'), s('click', 'remove-item'), s('click_if_enabled', 'remove-item'),
                 s('expect_text', 'cart-count', '0')],
        'accordion': [s('expect_attribute', 'faq-toggle', '{"name":"aria-expanded","value":"false"}'),
                      s('press', 'faq-toggle', 'Enter'), s('expect_visible', 'faq-answer'),
                      s('expect_attribute', 'faq-toggle', '{"name":"aria-expanded","value":"true"}'),
                      s('press', 'faq-toggle', 'Enter'), s('expect_hidden', 'faq-answer')],
        'stepper': [s('click', 'quantity-plus'), s('click', 'quantity-plus'), s('expect_text', 'quantity', '3'),
                    s('click', 'quantity-minus'), s('click', 'quantity-minus'), s('click_if_enabled', 'quantity-minus'),
                    s('expect_text', 'quantity', '1')],
        'theme': [s('record_palette', 'theme-toggle'), s('click', 'theme-toggle'), s('expect_text', 'theme-label', 'Night'),
                  s('expect_palette_changed', 'theme-toggle'), s('click', 'theme-toggle'),
                  s('expect_text', 'theme-label', 'Day'), s('expect_palette_restored', 'theme-toggle')],
        'sort': [s('expect_text', 'directory-item:first', 'Atlas'), s('select', 'sort', 'desc'),
                 s('expect_text', 'directory-item:first', 'Beacon'), s('fill', 'search', 'Atlas'),
                 s('expect_count', 'directory-item', '1'), s('fill', 'search', ''),
                 s('expect_count', 'directory-item', '2'), s('expect_text', 'directory-item:first', 'Beacon'),
                 s('select', 'sort', 'asc'), s('expect_text', 'directory-item:first', 'Atlas')],
        'dialog': [s('click', 'open-dialog'), s('expect_visible', 'note-dialog'), s('press', 'note-input', 'Escape'),
                   s('expect_hidden', 'note-dialog'), s('expect_focused', 'open-dialog'), s('click', 'open-dialog'),
                   s('fill', 'note-input', 'Second note'), s('click', 'save-note'), s('expect_hidden', 'note-dialog'),
                   s('expect_text', 'saved-note', 'Second note'), s('expect_focused', 'open-dialog')],
    }[kind]
    case['tests'].append({'id': f"{case['id']}-edge-cases", 'steps': extra})
    # Numeric readouts expose their value at these test targets. Substring checks
    # would incorrectly accept 13 when the required quantity is 3.
    if kind in {'stepper', 'cart'}:
        target = 'quantity' if kind == 'stepper' else 'cart-count'
        for test in case['tests']:
            for instruction in test['steps']:
                if instruction['action'] == 'expect_text' and instruction['test_id'] == target:
                    instruction['action'] = 'expect_text_exact'
    return case
