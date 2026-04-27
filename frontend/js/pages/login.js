import { h, clear } from '../utils.js';
import { api } from '../api.js';
import { setState } from '../state.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { field, textInput } from '../components/forms.js';

export function renderLogin(root) {
  clear(root);

  const submit = async (e) => {
    e.preventDefault();
    const email = e.target.email.value.trim();
    const password = e.target.password.value;
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Connexion…';
    try {
      const tok = await api.login(email, password);
      setState({ token: tok.access_token });
      const me = await api.me();
      setState({ user: me });
      toast.success('Connecté.');
      navigate('#/chat');
    } catch (err) {
      toast.error(err.detail || 'Identifiants invalides');
      btn.disabled = false;
      btn.textContent = 'Se connecter';
    }
  };

  const card = h('form', { class: 'auth-card', onSubmit: submit }, [
    h('div', { class: 'auth-brand' }, [
      h('img', { src: '/assets/logo.svg', alt: 'Sonar-Echo' }),
      h('h1', {}, 'Sonar-Echo'),
    ]),
    h('p', { class: 'muted text-sm mb-4' }, 'Connecte-toi pour accéder à tes bases de connaissance.'),
    field('Email', textInput({ name: 'email', type: 'email', required: true, autofocus: true, placeholder: 'admin@example.com' })),
    field('Mot de passe', textInput({ name: 'password', type: 'password', required: true })),
    h('button', { class: 'btn btn-primary w-full', type: 'submit' }, 'Se connecter'),
    h('div', { class: 'login-help' },
      'Pas de compte ? Les invitations sont émises par un administrateur via ' +
      "l'API REST ou le script de seed (cf. README)."),
  ]);

  root.appendChild(h('div', { class: 'auth-screen' }, [card]));
}
