export type Environment = {
  id: number;
  name: string;
  template: string;
  status: string;
  host_port?: number | null;
  delete_volume_on_delete?: boolean;
};
