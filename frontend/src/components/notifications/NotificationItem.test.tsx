import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import identity from "@/api/__fixtures__/backend-identity.json";
import type { AppNotification } from "@/api/types";
import { NotificationItem } from "./NotificationItem";

const list = identity.notifications_list as unknown as AppNotification[];
const team = list.find((n) => n.context)!;
const personal = list.find((n) => !n.context)!;

describe("NotificationItem : profil concerné (T6)", () => {
  it("notification d'équipe : badge « Organisation Atelier X »", () => {
    render(<NotificationItem notification={team} onOpen={() => {}} />);
    expect(screen.getByTestId("notification-context")).toHaveTextContent("Organisation Atelier X");
  });

  it("notification personnelle : aucun badge de profil", () => {
    render(<NotificationItem notification={personal} onOpen={() => {}} />);
    expect(screen.queryByTestId("notification-context")).not.toBeInTheDocument();
  });

  it("profil supprimé (nom nul) : le type seul, sans « null »", () => {
    render(<NotificationItem notification={{ ...team, context: { ...team.context!, name: null as unknown as string } }} onOpen={() => {}} />);
    expect(screen.getByTestId("notification-context")).toHaveTextContent(/^Organisation$/);
  });

  it("prestataire : badge « Prestataire … »", () => {
    render(<NotificationItem notification={{ ...team, context: { type: "PROVIDER", id: team.context!.id, name: "Marie couture" } }} onOpen={() => {}} />);
    expect(screen.getByTestId("notification-context")).toHaveTextContent("Prestataire Marie couture");
  });

  it("le clic ouvre la notification ; texte « Non lue » accessible", () => {
    const onOpen = vi.fn();
    render(<NotificationItem notification={team} onOpen={onOpen} />);
    expect(screen.getByLabelText("Non lue")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledWith(team);
  });
});
