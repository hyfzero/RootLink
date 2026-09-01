import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/app_state.dart';
import '../../domain/models.dart';
import '../shared/role_avatar.dart';

class HomePage extends ConsumerWidget {
  const HomePage({
    super.key,
    required this.onOpenChat,
    required this.onCreateRole,
    required this.onEditRole,
    required this.onImport,
    required this.isDark,
    required this.onToggleTheme,
  });

  final ValueChanged<CompanionRole> onOpenChat;
  final VoidCallback onCreateRole;
  final ValueChanged<CompanionRole> onEditRole;
  final VoidCallback onImport;
  final bool isDark;
  final VoidCallback onToggleTheme;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rolesState = ref.watch(rolesProvider);
    return CustomScrollView(
      slivers: <Widget>[
        SliverAppBar.large(
          title: const Text('RootLink'),
          actions: <Widget>[
            IconButton(
              onPressed: onToggleTheme,
              tooltip: isDark ? '切换到白天模式' : '切换到夜晚模式',
              icon: Icon(
                isDark ? Icons.light_mode_outlined : Icons.dark_mode_outlined,
              ),
            ),
            IconButton(
              onPressed: onImport,
              tooltip: '导入角色包',
              icon: const Icon(Icons.download_rounded),
            ),
            const SizedBox(width: 8),
          ],
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
          sliver: SliverList.list(
            children: <Widget>[
              _WelcomeCard(onCreateRole: onCreateRole),
              const SizedBox(height: 28),
              Row(
                children: <Widget>[
                  Text('你的角色', style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  TextButton.icon(
                    onPressed: onCreateRole,
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('新建'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
        if (rolesState.roles.isEmpty)
          SliverFillRemaining(
            hasScrollBody: false,
            child: _EmptyState(onCreate: onCreateRole, onImport: onImport),
          )
        else
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 40),
            sliver: SliverLayoutBuilder(
              builder: (context, constraints) {
                final columns = constraints.crossAxisExtent >= 900
                    ? 3
                    : constraints.crossAxisExtent >= 560
                    ? 2
                    : 1;
                return SliverGrid.builder(
                  itemCount: rolesState.roles.length,
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: columns,
                    crossAxisSpacing: 14,
                    mainAxisSpacing: 14,
                    mainAxisExtent: 178,
                  ),
                  itemBuilder: (context, index) {
                    final role = rolesState.roles[index];
                    return _RoleCard(
                      role: role,
                      onTap: () => onOpenChat(role),
                      onEdit: () => onEditRole(role),
                    );
                  },
                );
              },
            ),
          ),
      ],
    );
  }
}

class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard({required this.onCreateRole});
  final VoidCallback onCreateRole;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(24),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surface,
      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      borderRadius: BorderRadius.circular(18),
    ),
    child: Row(
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                '在每一次对话里，\n让关系慢慢生长。',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                '角色、记忆和聊天都只保存在你的设备上。',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: onCreateRole,
                icon: const Icon(Icons.auto_awesome_rounded),
                label: const Text('创建新角色'),
              ),
            ],
          ),
        ),
        Icon(
          Icons.hub_rounded,
          size: 92,
          color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.16),
        ),
      ],
    ),
  );
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({
    required this.role,
    required this.onTap,
    required this.onEdit,
  });
  final CompanionRole role;
  final VoidCallback onTap;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) => Card(
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          children: <Widget>[
            Row(
              children: <Widget>[
                RoleAvatar(role: role, radius: 31),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        role.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        role.statusText.isEmpty ? role.type : role.statusText,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: onEdit,
                  tooltip: '编辑角色',
                  icon: const Icon(Icons.more_horiz_rounded),
                ),
              ],
            ),
            const Spacer(),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                role.lastMessage.isEmpty ? role.intro : role.lastMessage,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  height: 1.45,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ),
            const Spacer(),
            Row(
              children: <Widget>[
                ...role.tags
                    .take(3)
                    .map(
                      (tag) => Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: Theme.of(
                              context,
                            ).colorScheme.primary.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(9),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            child: Text(
                              tag,
                              style: const TextStyle(fontSize: 11),
                            ),
                          ),
                        ),
                      ),
                    ),
                const Spacer(),
                if (role.lastTime.isNotEmpty)
                  Text(
                    role.lastTime,
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onCreate, required this.onImport});
  final VoidCallback onCreate;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.people_outline_rounded, size: 58),
          const SizedBox(height: 18),
          Text('还没有角色', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          const Text('创建一个新角色，或导入已有的 .amadues 角色包。'),
          const SizedBox(height: 20),
          Wrap(
            spacing: 10,
            children: <Widget>[
              FilledButton(onPressed: onCreate, child: const Text('创建角色')),
              OutlinedButton(onPressed: onImport, child: const Text('导入角色')),
            ],
          ),
        ],
      ),
    ),
  );
}
