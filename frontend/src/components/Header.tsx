import { Link } from "react-router";

function Header() {
  return (
    <header className="header">
      <Link className="logo" to="/">
        DevTest Hub
      </Link>

      <nav className="header-nav">
        <Link to="/">Главная</Link>
        <Link to="/login">Вход</Link>
        <Link to="/register">Регистрация</Link>
      </nav>
    </header>
  );
}

export default Header;
