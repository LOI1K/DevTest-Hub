type PlatformCardProps = {
  title: string;
  description: string;
  status: "ready" | "planned";
};

function PlatformCard({ title, description, status }: PlatformCardProps) {
  return (
    <article className="card">
      <h3>{title}</h3>
      <p>{description}</p>

      <span className={status === "ready" ? "status" : "status planned"}>
        {status === "ready" ? "Реализовано" : "В разработке"}
      </span>
    </article>
  );
}

export default PlatformCard;
