/**
 * Members list page with table, search, and filtering.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Chip,
    IconButton,
    InputAdornment,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
} from '@mui/material';
import {
    Add as AddIcon,
    Search as SearchIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    FaceRetouchingNatural as EnrollIcon,
    CardMembership as CardMembershipIcon,
} from '@mui/icons-material';
import { membersApi, Member } from '@/api/members';
import { useLanguage } from '@/i18n/LanguageContext';

export const MembersList: React.FC = () => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

    const deleteMutation = useMutation({
        mutationFn: (id: string) => membersApi.deleteMember(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setDeleteTarget(null);
        },
        onError: (error: any) => {
            alert(t.members.errorDeleting.replace('{error}', error?.response?.data?.detail || error?.message || 'Unknown'));
            setDeleteTarget(null);
        },
    });

    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(25);
    const [search, setSearch] = useState('');

    const { data, isLoading } = useQuery({
        queryKey: ['members', page, rowsPerPage, search],
        queryFn: () =>
            membersApi.getMembers({
                skip: page * rowsPerPage,
                limit: rowsPerPage,
                search: search || undefined,
            }),
    });

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active':
                return 'success';
            case 'inactive':
                return 'default';
            case 'suspended':
                return 'error';
            default:
                return 'default';
        }
    };

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4">{t.members.title}</Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => navigate('/members/new')}
                >
                    {t.members.addMember}
                </Button>
            </Box>

            <Card>
                <CardContent>
                    <TextField
                        fullWidth
                        placeholder={t.members.search}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon />
                                </InputAdornment>
                            ),
                        }}
                        sx={{ mb: 2 }}
                    />

                    <TableContainer>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>{t.members.name}</TableCell>
                                    <TableCell>{t.members.idNumber}</TableCell>
                                    <TableCell>{t.members.email}</TableCell>
                                    <TableCell>{t.members.phone}</TableCell>
                                    <TableCell>{t.members.status}</TableCell>
                                    <TableCell>{t.members.enrolled}</TableCell>
                                    <TableCell align="right">{t.common.actions}</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow>
                                        <TableCell colSpan={7} align="center">
                                            {t.members.loading}
                                        </TableCell>
                                    </TableRow>
                                ) : data?.members.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={7} align="center">
                                            {t.members.noMembersFound}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    data?.members.map((member: Member) => (
                                        <TableRow key={member.id} hover>
                                            <TableCell>
                                                {member.first_name} {member.last_name}
                                            </TableCell>
                                            <TableCell>{member.id_number || '—'}</TableCell>
                                            <TableCell>{member.email}</TableCell>
                                            <TableCell>{member.phone}</TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={member.status}
                                                    color={getStatusColor(member.status)}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={member.facial_data_enrolled ? t.members.yes : t.members.no}
                                                    color={member.facial_data_enrolled ? 'success' : 'default'}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell align="right">
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/edit`)}
                                                    title={t.members.editMember}
                                                    color="primary"
                                                >
                                                    <EditIcon />
                                                </IconButton>
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/membership`)}
                                                    title={t.members.assignMembership}
                                                    color="secondary"
                                                >
                                                    <CardMembershipIcon />
                                                </IconButton>
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/enroll`)}
                                                    title={t.members.faceEnrollment}
                                                    color={member.facial_data_enrolled ? 'success' : 'warning'}
                                                >
                                                    <EnrollIcon />
                                                </IconButton>
                                                <IconButton size="small" title={t.members.delete} color="error" onClick={() => setDeleteTarget(member.id)}>
                                                    <DeleteIcon />
                                                </IconButton>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>

                    <TablePagination
                        component="div"
                        count={data?.total || 0}
                        page={page}
                        onPageChange={(_, newPage) => setPage(newPage)}
                        rowsPerPage={rowsPerPage}
                        onRowsPerPageChange={(e) => {
                            setRowsPerPage(parseInt(e.target.value, 10));
                            setPage(0);
                        }}
                    />
                </CardContent>
            </Card>
            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
                <DialogTitle>{t.members.deleteMember}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t.members.deleteConfirmMsg}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDeleteTarget(null)}>{t.members.cancel}</Button>
                    <Button
                        onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
                        color="error"
                        variant="contained"
                        disabled={deleteMutation.isPending}
                    >
                        {deleteMutation.isPending ? t.members.deleting : t.members.delete}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
