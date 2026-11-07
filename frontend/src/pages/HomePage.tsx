import PlatformCard from "../components/PlatformCard";

const platformComponents = [
  {
    title: "REST API",
    description: "FastAPI — серверная часть платформы.",
    status: "ready",
  },
  {
    title: "PostgreSQL",
    description: "Хранение пользователей и тестовых сред.",
    status: "ready",
  },
  {
    title: "Docker Worker",
    description: "Автоматическое развёртывание контейнеров.",
    status: "planned",
  },
] as const;

function HomePage() {
  return (
    <main className="main">
      <div className="eyebrow">Панель управления</div>

      <h1>Тестовые среды разработчиков</h1>

      <p className="description">
        Создавайте и управляйте изолированными средами для разработки и
        тестирования.
      </p>

      <section className="section">
        <h2>Компоненты платформы</h2>

        <div className="cards">
          {platformComponents.map((component) => (
            <PlatformCard
              key={component.title}
              title={component.title}
              description={component.description}
              status={component.status}
            />
          ))}
        </div>
      </section>
    </main>
  );
}

export default HomePage;
