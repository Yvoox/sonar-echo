// Form field helpers.
import { h } from '../utils.js';

export function field(label, input, hint) {
  return h('div', { class: 'field' }, [
    label ? h('label', {}, label) : null,
    input,
    hint ? h('small', { class: 'subtle text-xs' }, hint) : null,
  ]);
}

export function textInput({ name, value = '', placeholder = '', type = 'text', required = false, autofocus = false, onInput } = {}) {
  return h('input', {
    class: 'input', type, name, placeholder,
    value, required, autofocus,
    onInput: (e) => onInput?.(e.target.value, e),
  });
}

export function textArea({ name, value = '', placeholder = '', rows = 4, onInput } = {}) {
  const el = h('textarea', {
    class: 'textarea', name, placeholder, rows,
    onInput: (e) => onInput?.(e.target.value, e),
  });
  el.value = value;
  return el;
}

export function select({ name, value, options = [], onChange } = {}) {
  const el = h('select', {
    class: 'select', name,
    onChange: (e) => onChange?.(e.target.value, e),
  }, options.map(o => h('option', {
    value: o.value, selected: o.value === value,
  }, o.label)));
  return el;
}

export function form({ children = [], onSubmit }) {
  return h('form', {
    onSubmit: (e) => { e.preventDefault(); onSubmit?.(formDataToJson(e.target)); },
  }, children);
}

export function formDataToJson(formEl) {
  const data = {};
  for (const [k, v] of new FormData(formEl)) {
    if (k in data) data[k] = [].concat(data[k], v);
    else data[k] = v;
  }
  return data;
}
